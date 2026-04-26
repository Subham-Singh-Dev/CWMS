from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from django.utils import timezone

from attendance.models import Attendance
from employees.models import Employee
from analytics.services.audit_service import recent_activity_items_for_manager
from .serializers import AttendanceSerializer, EmployeeSerializer


class RecentActivityAPIView(APIView):
    """
    GET /api/activity/
    Returns recent audit log activity for manager dashboard.
    Replaces: manager_recent_activity_api JsonResponse view
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # Same logic as your existing view — just DRF style
        is_manager = (
            request.user.is_superuser or
            request.user.groups.filter(name='Manager').exists()
        )
        if not is_manager:
            return Response(
                {"error": "Permission denied"},
                status=status.HTTP_403_FORBIDDEN
            )

        activities = recent_activity_items_for_manager(limit=8)
        return Response({"activities": activities})


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