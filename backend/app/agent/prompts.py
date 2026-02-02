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

Learned preferences (apply if present): {prompt_delta}
- If avoid_domains: strongly penalize those domains (score < 0.3)
- If prefer_domains: boost those domains (score + 0.2)
- If search_focus: prioritize results matching that focus

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

LEARNER_PROMPT = """You are a machine learning system that improves an AI agent's browsing strategy based on user feedback.

TASK: Analyze the run trace and user feedback, then propose a precise patch to improve future runs.

USER FEEDBACK:
{feedback}

RUN TRACE (what the agent did):
{trace}

INSTRUCTIONS:
1. Read the feedback tags and notes carefully
2. Analyze what went wrong in the trace
3. Propose specific, measurable changes

POLICY_DELTA (adjust search parameters):
- max_tabs: int (1-20) - Number of results to open
  * If "too_many_results" or "too_many_tabs": set to 5-7
  * If "too_few_results": set to 12-15
  * Default: leave unchanged

- min_score: float (0.0-1.0) - Minimum quality threshold
  * If "low_quality" or "irrelevant": set to 0.70-0.80
  * If "high_quality" or "perfect": set to 0.50-0.60
  * Default: leave unchanged

- unique_domains: int (0 or 1) - Whether to enforce domain diversity
  * Set to 1 if user wants variety
  * Set to 0 if user wants depth from same sources

PROMPT_DELTA (adjust LLM scoring behavior):
- search_focus: string - What to prioritize
  * Examples: "user reviews", "technical specs", "price comparisons", "official docs"
  
- avoid_domains: list[string] - Domains to penalize in scoring
  * Extract from notes if user says "no [domain]", "avoid [domain]", "not [domain]"
  * Examples: ["amazon.com", "ebay.com"] if user doesn't want marketplaces
  
- prefer_domains: list[string] - Domains to boost in scoring
  * Extract if user mentions preferring certain sites
  * Examples: ["reddit.com", "wirecutter.com"] for reviews

CRITICAL RULES:
- Only include fields that need to change
- Use exact numeric types (int for max_tabs, float for min_score)
- Keep domain lists short (max 5 items each)
- Rationale must explain WHY you made each change
- If feedback is unclear, make conservative adjustments

EXAMPLE OUTPUT:
{{
  "policy_delta": {{"max_tabs": 5, "min_score": 0.75}},
  "prompt_delta": {{"avoid_domains": ["amazon.com"], "prefer_domains": ["reddit.com"], "search_focus": "user reviews and comparisons"}},
  "rationale": "User complained about too many marketplace results. Reduced max_tabs from 11 to 5, raised quality threshold to 0.75, and configured scorer to avoid marketplaces while preferring review sites."
}}

{format_instructions}
"""
