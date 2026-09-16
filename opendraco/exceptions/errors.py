class OpendracoError(Exception):
    pass


class ConfigError(OpendracoError):
    pass


class TopologyError(OpendracoError):
    pass


class RepoCloneError(OpendracoError):
    pass


class LocalizationError(OpendracoError):
    pass


class PatchGenerationError(OpendracoError):
    pass


class ValidationError(OpendracoError):
    pass


class AgentExecutionError(OpendracoError):
    pass


class OllamaMemoryError(OpendracoError):
    """Ollama refused to load the model because system memory is insufficient."""
    pass
