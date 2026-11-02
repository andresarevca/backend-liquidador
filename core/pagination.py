from rest_framework.pagination import PageNumberPagination


class StandardPagination(PageNumberPagination):
    """Paginación por defecto; el cliente puede pedir ?page_size=N (máx. 100)."""

    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100
