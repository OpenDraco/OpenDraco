class EvomasError(Exception):
    pass


class ConfigError(EvomasError):
    pass


class TopologyError(EvomasError):
    pass


class RepoCloneError(EvomasError):
    pass


class LocalizationError(EvomasError):
    pass


class PatchGenerationError(EvomasError):
    pass


class ValidationError(EvomasError):
    pass


class AgentExecutionError(EvomasError):
    pass


class OllamaMemoryError(EvomasError):
    """Ollama refused to load the model because system memory is insufficient."""
    pass
