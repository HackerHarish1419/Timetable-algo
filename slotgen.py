import random
import pandas as pd

num_teachers = 571
num_days = 5
categories = [0, 1, 2]  # 0 = Morning, 1 = Afternoon, 2 = Evening

def is_valid_schedule(schedule):
    # Constraint 1: category counts between 1–2
    for cat in categories:
        if not (1 <= schedule.count(cat) <= 2):
            return False

    # Constraint 2: No evening followed by morning
    for i in range(len(schedule) - 1):
        if schedule[i] == 2 and schedule[i + 1] == 0:
            return False

    return True

teacher_schedules = {}

for teacher_id in range(1, num_teachers + 1):
    valid = False
    while not valid:
        schedule = [random.choice(categories) for _ in range(num_days)]
        valid = is_valid_schedule(schedule)
    teacher_schedules[teacher_id] = schedule

# Convert to DataFrame
df = pd.DataFrame.from_dict(teacher_schedules, orient="index", columns=[f"day_{i}" for i in range(num_days)])
df.index.name = "teacher"

# Save or display
df.reset_index(inplace=True)
df.to_csv("simulated_teacher_schedule.csv", index=False)
print("✅ Generated and saved simulated_teacher_schedule.csv")
