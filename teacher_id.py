import pandas as pd
from difflib import get_close_matches

# Load files
course_df = pd.read_csv("course_mapping_output.csv")
teacher_df = pd.read_csv("Teacher-2025-05-06.csv")

# Step 1: Combine teacher name and clean it
def clean_name(first, last):
    full = f"{first} {last}".lower().strip()
    full = full.replace("mr. ", "").replace("mrs. ", "").replace("dr. ", "")
    return ' '.join(full.split())  # normalize spaces

teacher_df["full_name_clean"] = teacher_df.apply(
    lambda row: clean_name(row["teacher_id__first_name"], row["teacher_id__last_name"]), axis=1
)

# Step 2: Clean Faculty names similarly
def clean_faculty_name(name):
    return ' '.join(name.lower().strip().split())

course_df["Faculty_clean"] = course_df["Faculty"].apply(clean_faculty_name)

# Step 3: Fuzzy match Faculty names to teacher full names
def get_best_match(name, choices, cutoff=0.75):
    matches = get_close_matches(name, choices, n=1, cutoff=cutoff)
    return matches[0] if matches else None

teacher_names = teacher_df["full_name_clean"].tolist()
course_df["matched_teacher_name"] = course_df["Faculty_clean"].apply(lambda x: get_best_match(x, teacher_names))

# Step 4: Merge to get IDs
merged_df = pd.merge(course_df, teacher_df[["id", "full_name_clean"]],
                     left_on="matched_teacher_name", right_on="full_name_clean", how="left")

# Step 5: Final output
final_df = merged_df[["course_code", "Faculty", "lecture_hours", "tutorial_hours",
                      "practical_hours", "credits", "id"]]

# Save or display
final_df.to_csv("matched_course_teacher-1.csv", index=False)
print("✅ Merged data saved to 'matched_course_teacher-1.csv'")
