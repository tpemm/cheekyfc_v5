"""Foundation services for the modular Fantrax analytics platform."""

from core.services.dataset_registry import (
    DatasetRegistry,
    RegistryValidationError,
)
from core.services.operations_service import (
    OperationNotAllowedError,
    OperationParameterError,
    OperationsService,
    OperationsServiceError,
    UnknownOperationError,
)
from core.services.season_manager import (
    SeasonCatalogError,
    SeasonManager,
    SeasonMutationError,
)

__all__ = [
    "DatasetRegistry",
    "OperationNotAllowedError",
    "OperationParameterError",
    "OperationsService",
    "OperationsServiceError",
    "RegistryValidationError",
    "SeasonCatalogError",
    "SeasonManager",
    "SeasonMutationError",
    "UnknownOperationError",
]
