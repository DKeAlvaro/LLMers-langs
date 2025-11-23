import json
import os
import re
import pytest

def get_lesson_files():
    lesson_files = []
    lessons_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'lessons')
    for root, _, files in os.walk(lessons_dir):
        for file in files:
            if file.endswith('.json'):
                lesson_files.append(os.path.join(root, file))
    return lesson_files

@pytest.mark.parametrize("lesson_file", get_lesson_files())
def test_lesson_structure(lesson_file):
    with open(lesson_file, 'r', encoding='utf-8') as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError as e:
            pytest.fail(f"{lesson_file} is not a valid JSON file: {e}")

    if "content" in data:
        for i, item in enumerate(data["content"]):
            if item.get("type") == "interactive_scenario" and "conversation_flow" in item:
                for j, step in enumerate(item["conversation_flow"]):
                    if "user_response" in step and "title" in step["user_response"]:
                        pytest.fail(
                            f"File: {lesson_file}\n"
                            f"Content item {i}, Step {j}: 'title' should not be in 'user_response'"
                        )

@pytest.mark.parametrize("lesson_file", get_lesson_files())
def test_interactive_scenario_variable_usage(lesson_file):
    """
    Tests that a scenario step with 'extract_info' does not use variables in its own chatbot_message
    that are being defined in the same step.
    """
    with open(lesson_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    if "content" not in data:
        return

    for i, item in enumerate(data["content"]):
        if item.get("type") == "interactive_scenario" and "conversation_flow" in item:
            for j, step in enumerate(item["conversation_flow"]):
                if "extract_info" in step and "chatbot_message" in step:
                    variables = re.findall(r'\{(.*?)\}', step["chatbot_message"])
                    if not variables:
                        continue

                    for var in variables:
                        if var in step["extract_info"]:
                            pytest.fail(
                                f"File: {lesson_file}\n"
                                f"Content item {i} ('{item.get('title', 'N/A')}'), Step {j}: "
                                f"The 'chatbot_message' in a step with 'extract_info' should not contain variables "
                                f"that are defined in the same step. Variable '{var}' is defined and used in the same step."
                            )
