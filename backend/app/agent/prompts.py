PLANNER_PROMPT = """You are the planning module for a web-buying agent.
Convert the user goal into:
1) search queries (3 concise queries)
2) product evaluation rubric with weights (0-1)
3) required source types (official specs, reputable review, retailer)
4) extraction schema fields

User goal: {goal}
Search hint: {query}
Prompt deltas (if any): {prompt_delta}

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

LINK_SCORER_PROMPT = """You are scoring search results for relevance and credibility.
Score each item from 0 to 1 and provide a short reason.
Prefer: official specs, reputable reviews, known retailers.
Penalize: affiliate listicles, spam, thin content, duplicates.

User goal: {goal}
Query: {query}
Required source types: {required_sources}

Return JSON: {format_instructions}

Items:
{items}
"""

SUMMARY_PROMPT = """You are a product analyst. Using the extracted items, pick the top 3 and recommend 1.
Return a JSON object with:
- top_three: list of 3 items with fields {name, price, reasons}
- recommendation: {name, reason}
- table: list of rows (dict) for comparison with the extraction fields

User goal: {goal}
Extracted items:
{items}

{format_instructions}
"""

LEARNER_PROMPT = """You are improving the agent's browsing strategy based on feedback.
Given the run trace and user feedback, propose a patch.
Return JSON with:
- policy_delta: {max_tabs?, min_score?, unique_domains?}
- prompt_delta: {search_focus?, avoid_domains?, prefer_domains?}
- rationale: short string

Trace:
{trace}

Feedback:
{feedback}

{format_instructions}
"""
