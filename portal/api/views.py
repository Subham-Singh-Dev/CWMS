from rest_framework.views import APIView
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from django.utils import timezone

from attendance.models import Attendance
from employees.models import Employee
from analytics.services.audit_service import recent_activity_items_for_manager
from .serializers import AttendanceSerializer, EmployeeSerializer

from payroll.models import MonthlySalary, Advance
from .serializers import MonthlySalarySerializer, AdvanceSerializer
from django.core.cache import cache


class RecentActivityAPIView(APIView):
    """
    GET /api/activity/
    Redis cached — 5 minute TTL
    Cache key: cwms:activity:manager
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        is_manager = (
            request.user.is_superuser or
            request.user.groups.filter(name='Manager').exists()
        )
        if not is_manager:
            return Response(
                {"error": "Permission denied"},
                status=status.HTTP_403_FORBIDDEN
            )

        # Try cache first
        cache_key = f"activity:manager:{request.user.id}"
        cached = cache.get(cache_key)

        if cached:
            return Response({
                "activities": cached,
                "cached": True      # tells you it came from Redis
            })

        # Cache miss — hit database
        activities = recent_activity_items_for_manager(limit=8)

        # Store in Redis for 5 minutes
        cache.set(cache_key, activities, timeout=300)

        return Response({
            "activities": activities,
            "cached": False     # tells you it came from DB
        })


class AttendanceListAPIView(APIView):
    """
    GET  /api/attendance/?date=2026-04-26  → list attendance for a date
    POST /api/attendance/                  → mark single attendance
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        is_manager = (
            request.user.is_superuser or
            request.user.groups.filter(name='Manager').exists()
        )
        if not is_manager:
            return Response(
                {"error": "Permission denied"},
                status=status.HTTP_403_FORBIDDEN
            )

        # Filter by date if provided
        date_str = request.query_params.get('date')
        if date_str:
            try:
                from datetime import datetime
                filter_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            except ValueError:
                return Response(
                    {"error": "Invalid date format. Use YYYY-MM-DD"},
                    status=status.HTTP_400_BAD_REQUEST
                )
        else:
            filter_date = timezone.now().date()

        attendance = Attendance.objects.filter(
            date=filter_date
        ).select_related('employee')

        serializer = AttendanceSerializer(attendance, many=True)
        return Response({
            "date": filter_date,
            "count": attendance.count(),
            "attendance": serializer.data
        })

    def post(self, request):
        is_manager = (
            request.user.is_superuser or
            request.user.groups.filter(name='Manager').exists()
        )
        if not is_manager:
            return Response(
                {"error": "Permission denied"},
                status=status.HTTP_403_FORBIDDEN
            )

        serializer = AttendanceSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(
                serializer.data,
                status=status.HTTP_201_CREATED
            )
        return Response(
            serializer.errors,
            status=status.HTTP_400_BAD_REQUEST
        )


class EmployeeListAPIView(APIView):
    """
    GET /api/employees/ → list all active employees
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        is_manager = (
            request.user.is_superuser or
            request.user.groups.filter(name='Manager').exists()
        )
        if not is_manager:
            return Response(
                {"error": "Permission denied"},
                status=status.HTTP_403_FORBIDDEN
            )

        employees = Employee.objects.filter(
            is_active=True
        ).order_by('name')

        serializer = EmployeeSerializer(employees, many=True)
        return Response({
            "count": employees.count(),
            "employees": serializer.data
        })

class PayrollListAPIView(APIView):
    """
    GET /api/payroll/?month=2026-04
    Returns salary list for a given month.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        is_manager = (
            request.user.is_superuser or
            request.user.groups.filter(name='Manager').exists()
        )
        if not is_manager:
            return Response(
                {"error": "Permission denied"},
                status=status.HTTP_403_FORBIDDEN
            )

        month_str = request.query_params.get('month')
        if month_str:
            try:
                from datetime import datetime
                month = datetime.strptime(month_str, '%Y-%m').date().replace(day=1)
            except ValueError:
                return Response(
                    {"error": "Invalid month format. Use YYYY-MM"},
                    status=status.HTTP_400_BAD_REQUEST
                )
        else:
            month = timezone.now().date().replace(day=1)

        salaries = MonthlySalary.objects.filter(
            month=month
        ).select_related('employee').order_by('employee__name')

        serializer = MonthlySalarySerializer(salaries, many=True)
        return Response({
            "month": str(month),
            "count": salaries.count(),
            "salaries": serializer.data
        })


class AdvanceListAPIView(APIView):
    """
    GET /api/advances/?employee_id=1  → list advances for employee
    POST /api/advances/               → issue new advance
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        is_manager = (
            request.user.is_superuser or
            request.user.groups.filter(name='Manager').exists()
        )
        if not is_manager:
            return Response(
                {"error": "Permission denied"},
                status=status.HTTP_403_FORBIDDEN
            )

        employee_id = request.query_params.get('employee_id')
        queryset = Advance.objects.select_related('employee')

        if employee_id:
            queryset = queryset.filter(employee_id=employee_id)

        queryset = queryset.order_by('issued_date')
        serializer = AdvanceSerializer(queryset, many=True)
        return Response({
            "count": queryset.count(),
            "advances": serializer.data
        })

    def post(self, request):
        is_manager = (
            request.user.is_superuser or
            request.user.groups.filter(name='Manager').exists()
        )
        if not is_manager:
            return Response(
                {"error": "Permission denied"},
                status=status.HTTP_403_FORBIDDEN
            )

        serializer = AdvanceSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(
                serializer.data,
                status=status.HTTP_201_CREATED
            )
        return Response(
            serializer.errors,
            status=status.HTTP_400_BAD_REQUEST
        )

class EmployeeDetailView(APIView):
    """
    GET    /api/employees/<pk>/  — retrieve one employee
    PUT    /api/employees/<pk>/  — partial update
    DELETE /api/employees/<pk>/  — remove employee
    """
    permission_classes = [IsAuthenticated]
    serializer_class = EmployeeSerializer

    def get(self, request, pk):
        employee = get_object_or_404(Employee, pk=pk)
        serializer = EmployeeSerializer(employee)
        return Response(serializer.data)

    def put(self, request, pk):
        employee = get_object_or_404(Employee, pk=pk)
        serializer = EmployeeSerializer(
            employee,
            data=request.data,
            partial=True        # PATCH-style: only update sent fields
        )
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        employee = get_object_or_404(Employee, pk=pk)
        employee.delete()
        return Response(
            {"message": "Employee deleted successfully."},
            status=status.HTTP_204_NO_CONTENT
        )