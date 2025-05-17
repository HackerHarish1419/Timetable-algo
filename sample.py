import pandas as pd

# Load the CSV files
teachers_df = pd.read_csv("data_teacher.csv")
courses_df = pd.read_csv("courses.csv")

# Normalize course codes for accurate matching
teachers_df['Code'] = teachers_df['Code'].astype(str).str.strip().str.upper()
courses_df['course_code'] = courses_df['course_code'].astype(str).str.strip().str.upper()

# Merge on course codes
merged_df = pd.merge(
    teachers_df,
    courses_df,
    left_on='Code',
    right_on='course_code',
    how='inner'
)

# Select only required columns
result = merged_df[['course_code', 'Faculty', 'lecture_hours', 'tutorial_hours', 'practical_hours', 'credits']]

# Save to a new CSV
result.to_csv("course_mapping_output.csv", index=False)

print("✅ Output saved as course_mapping_output.csv")
