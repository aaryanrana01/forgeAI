### SYSTEM
You turn structured test specifications into natural user questions.

### USER
THE ASSISTANT: $scope
TABLE ROW: $row
TASK: $task

Write ONE natural question a user would type for this task. It must mention the item so it can be
found (use its id "$item_id" and/or its name). Do not include the answer.

Return {"question": "..."}
