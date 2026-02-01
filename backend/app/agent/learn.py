import json
from app.agent.prompts import LEARNER_PROMPT
from app.services.llm_factory import get_chat_model
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from pydantic import BaseModel


class LearnOutput(BaseModel):
    policy_delta: dict
    prompt_delta: dict
    rationale: str


def generate_patch(trace: list, feedback: dict) -> dict:
    try:
        llm = get_chat_model()
        parser = JsonOutputParser(pydantic_object=LearnOutput)
        prompt = PromptTemplate(
            template=LEARNER_PROMPT,
            input_variables=["trace", "feedback"],
            partial_variables={"format_instructions": parser.get_format_instructions()},
        )
        message = prompt.format(
            trace=json.dumps(trace)[:12000],
            feedback=json.dumps(feedback)[:4000]
        )
        response = llm.invoke(message)
        text = response.content if hasattr(response, "content") else str(response)
        patch = parser.parse(text)
        return patch if isinstance(patch, dict) else patch.model_dump()
    except Exception as e:
        print(f"[LEARN] Patch generation failed: {e}")
        import traceback
        traceback.print_exc()
        # Return empty patch instead of crashing
        return {
            "policy_delta": {},
            "prompt_delta": {},
            "rationale": f"Error generating patch: {str(e)}"
        }
