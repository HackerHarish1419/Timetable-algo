# Re-import necessary library and reload uploaded files after state reset
import pandas as pd

# Re-load the uploaded files
course_teacher_df = pd.read_csv("matched_course_teacher-1.csv")
schedule_df = pd.read_csv("simulated_teacher_schedule.csv")

# Merge on teacher ID
merged_df = pd.merge(course_teacher_df, schedule_df, left_on="id", right_on="teacher", how="left")

# Drop the redundant 'teacher' column after merge
merged_df.drop(columns=["teacher"], inplace=True)

# Reorder columns as specified
final_columns = ["course_code", "Faculty", "lecture_hours", "tutorial_hours", "practical_hours", "credits", "id",
                 "day_0", "day_1", "day_2", "day_3", "day_4"]

# Reorder and display the final DataFrame
final_df = merged_df[final_columns]
final_df.head()
