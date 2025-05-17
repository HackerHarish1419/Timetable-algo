import pandas as pd

# Load all three files
df_rooms = pd.read_csv("rooms.csv")
df_courses = pd.read_csv("course_mapping_output.csv")
df_timetable = pd.read_csv("venues.csv")

# Clean up whitespace in important fields
df_courses["Faculty"] = df_courses["Faculty"].str.strip()
df_timetable["Faculty"] = df_timetable["Faculty"].str.strip()
df_timetable["Course Code"] = df_timetable["Course Code"].str.strip()
df_courses["course_code"] = df_courses["course_code"].str.strip()
df_timetable["Venue"] = df_timetable["Venue"].str.strip()

# Merge course and timetable data on course code and faculty name
merged = pd.merge(
    df_courses,
    df_timetable,
    left_on=["course_code", "Faculty"],
    right_on=["Course Code", "Faculty"],
    how="inner"
)

# Match room information:
# For simplicity, match on df_timetable["Venue"] == df_rooms["description"] or df_rooms["room_number"]
df_rooms["description"] = df_rooms["description"].fillna("").str.strip()
df_rooms["room_number"] = df_rooms["room_number"].str.strip()
df_timetable["Venue"] = df_timetable["Venue"].fillna("").str.strip()

# First try matching venue with room_number
room_matched = pd.merge(
    merged,
    df_rooms,
    left_on="Venue",
    right_on="room_number",
    how="left",
    suffixes=('', '_from_room_number')
)

# If no match on room_number, try matching with description
unmatched = room_matched[room_matched["room_number"].isna()]
matched_by_description = pd.merge(
    unmatched.drop(columns=df_rooms.columns, errors='ignore'),
    df_rooms,
    left_on="Venue",
    right_on="description",
    how="left",
    suffixes=('', '_from_description')
)

# Combine both matched data
final_matched = pd.concat([
    room_matched[~room_matched["room_number"].isna()],
    matched_by_description
], ignore_index=True)

# Select and rename the required columns
final_output = final_matched[[
    "course_code", "Faculty", "lecture_hours", "tutorial_hours", "practical_hours", "credits",
    "room_number", "block", "description", "is_lab", "room_type",
    "room_min_cap", "room_max_cap", "tech_level", "Venue"
]]

# Save or display the result
final_output.to_csv("final_output.csv", index=False)
print(final_output)
