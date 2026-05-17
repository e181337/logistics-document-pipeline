class PipelineError(Exception):
    retryable = True


class RetryablePipelineError(PipelineError):
    retryable = True


class NonRetryablePipelineError(PipelineError):
    retryable = False
