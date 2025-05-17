


import pandas as pd

# Load the CSV files
file1 = pd.read_csv('aiml_courses.csv')
file2 = pd.read_csv('course_mapping_output.csv')

# Strip any extra spaces
file1['Code'] = file1['Code'].str.strip()
file1['Department'] = file1['Department'].str.strip()
file2['course_code'] = file2['course_code'].str.strip()

# Filter file1 to only include rows from AIML department
file1_aiml = file1[file1['Department'] == 'AIML']

# Perform the merge
merged = pd.merge(file1_aiml, file2, left_on='Code', right_on='course_code')

# Save the result
merged.to_csv('matched_aiml_courses.csv', index=False)

print("Filtered AIML matched data saved to matched_aiml_courses.csv")
