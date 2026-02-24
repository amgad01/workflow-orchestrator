from prometheus_client import Counter, Gauge, Histogram

from src.ports.secondary.metrics import IMetrics


class MetricsRegistry(IMetrics):
    """Prometheus metrics registry."""

    def __init__(self):
        # Workflow metrics
        self.WORKFLOW_SUBMISSIONS_TOTAL = Counter(
            "workflow_submissions_total", "Total number of workflow submissions", ["workflow_name"]
        )

        self.WORKFLOW_COMPLETIONS_TOTAL = Counter(
            "workflow_completions_total",
            "Total number of workflow completions",
            ["workflow_id", "status"],
        )

        self.WORKFLOW_DURATION_SECONDS = Histogram(
            "workflow_duration_seconds",
            "Time taken for workflow to complete",
            ["workflow_id"],
            buckets=(1, 5, 10, 30, 60, 120, 300, 600),
        )

        # API metrics
        self.API_REQUEST_DURATION_SECONDS = Histogram(
            "api_request_duration_seconds",
            "Duration of API requests in seconds",
            ["endpoint", "method"],
            buckets=(0.01, 0.05, 0.1, 0.5, 1.0, 2.5, 5.0),
        )

        # Infrastructure metrics
        self.REDIS_STREAM_PENDING_MESSAGES = Gauge(
            "redis_stream_pending_messages",
            "Number of pending messages in Redis streams",
            ["stream_name", "group_name"],
        )

        # Node metrics
        self.NODE_EXECUTIONS_TOTAL = Counter(
            "node_executions_total", "Total number of node executions", ["handler", "status"]
        )

        self.NODE_DURATION_SECONDS = Histogram(
            "node_duration_seconds",
            "Time taken for node to complete",
            ["handler"],
            buckets=(0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0),
        )

    def record_submission(self, workflow_name: str):
        self.WORKFLOW_SUBMISSIONS_TOTAL.labels(workflow_name=workflow_name).inc()

    def record_workflow_completion(self, workflow_id: str, status: str, duration: float):
        self.WORKFLOW_COMPLETIONS_TOTAL.labels(workflow_id=workflow_id, status=status).inc()
        self.WORKFLOW_DURATION_SECONDS.labels(workflow_id=workflow_id).observe(duration)

    def record_node_completion(self, handler: str, status: str, duration: float):
        self.NODE_EXECUTIONS_TOTAL.labels(handler=handler, status=status).inc()
        self.NODE_DURATION_SECONDS.labels(handler=handler).observe(duration)

    def record_api_duration(self, endpoint: str, method: str, duration: float):
        self.API_REQUEST_DURATION_SECONDS.labels(endpoint=endpoint, method=method).observe(duration)

    def update_pending_messages(self, stream: str, group: str, count: int):
        self.REDIS_STREAM_PENDING_MESSAGES.labels(stream_name=stream, group_name=group).set(count)


# Global registry instance for adapter/framework layer
metrics_registry = MetricsRegistry()
