from prometheus_client import Counter, Histogram

prompts_total = Counter("prompts_total", "Total prompts processed", ["decision"])
prompts_blocked_total = Counter("prompts_blocked_total", "Blocked prompts", ["reason"])
prompt_pipeline_duration = Histogram(
    "prompt_pipeline_duration_seconds",
    "Prompt pipeline duration",
    buckets=[0.05, 0.1, 0.2, 0.3, 0.5, 1.0],
)
