import logging

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

logger = logging.getLogger(__name__)


def custom_exception_handler(exc, context):
    response = drf_exception_handler(exc, context)

    if response is not None:
        response.data['error_code'] = getattr(exc, 'default_code', 'error')
    else:
        logger.exception(f"Unhandled exception: {exc}")
        response = Response(
            {
                'detail': 'An internal server error occurred.',
                'error_code': 'server_error'
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

    return response
