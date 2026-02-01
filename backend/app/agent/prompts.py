PLANNER_PROMPT = """You are the planning module for a web-buying agent.
Convert the user goal into:
1) search queries (3 concise queries)
2) product evaluation rubric with weights (0-1)
3) required source types (official specs, reputable review, retailer)
4) extraction schema fields

User goal: {goal}
Search hint: {query}

{format_instructions}
"""

EXTRACTOR_PROMPT = """You are extracting structured data from a web page.
Return JSON with a single key "data" whose value is an object mapping fields to values.
If a field is missing, use null.

Fields to extract:
{fields}

Page URL: {url}
Page Title: {title}
Page Text (truncated):
{content}

{format_instructions}
"""
