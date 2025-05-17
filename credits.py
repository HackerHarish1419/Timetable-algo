import pandas as pd

# Load the CSV file
df = pd.read_csv('file_01.csv')

# Filter rows where Credits are between 1 and 5 inclusive
df_filtered = df[(df['Credits'] >= 1) & (df['Credits'] <= 5)]

# Save the filtered DataFrame back to a CSV (optional)
df_filtered.to_csv('filtered_file1.csv', index=False)

# Display the filtered DataFrame
print(df_filtered)
