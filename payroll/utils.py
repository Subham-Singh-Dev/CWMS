from io import BytesIO
from django.template.loader import render_to_string
from xhtml2pdf import pisa

def generate_payslip_pdf(salary):
    """
    Pure utility function. 
    Input: MonthlySalary object
    Output: PDF Bytes
    """
    # 1. Render HTML
    html_string = render_to_string('payroll/payslip.html', {'salary': salary})
    
    # 2. Create in-memory buffer
    result = BytesIO()
    
    # 3. Generate PDF
    pisa_status = pisa.CreatePDF(html_string, dest=result)
    
    # 4. Return bytes or None
    if pisa_status.err:
        return None
    
    return result.getvalue()