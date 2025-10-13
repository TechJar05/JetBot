from rest_framework.pagination import CursorPagination

class ReportCursorPagination(CursorPagination):
    page_size = 10  # default number of reports per page
    ordering = '-created_at'  # newest first
    cursor_query_param = 'cursor'  # ?cursor=xyz in URL
