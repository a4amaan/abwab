import logging

from rest_framework import status
from rest_framework.exceptions import (
    ValidationError,
    NotFound,
    APIException,
)
from rest_framework.response import Response
from rest_framework.views import exception_handler

logger = logging.getLogger(__name__)


def custom_exception_handler(exc, context):
    response = exception_handler(exc, context)

    if response is None:
        # Unhandled exceptions
        return Response(
            {
                "success": False,
                "error": {
                    "code": "server_error",
                    "message": "Internal server error",
                }
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    error_response = {
        "success": False,
        "error": {
            "code": "error",
            "message": "Request failed",
            "details": None,
        }
    }

    # Validation errors
    if isinstance(exc, ValidationError):
        error_response["error"] = {
            "code": "validation_error",
            "message": "Invalid input data",
            "details": response.data,
        }

    # Not found
    elif isinstance(exc, NotFound):
        error_response["error"] = {
            "code": "not_found",
            "message": str(exc),
        }

    # Other DRF exceptions
    elif isinstance(exc, APIException):
        error_response["error"] = {
            "code": exc.default_code,
            "message": str(exc),
            "details": response.data,
        }

    return Response(error_response, status=response.status_code)
