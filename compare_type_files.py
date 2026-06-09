import csv

def compare_type_files_to_csv(file1_path, file2_path, output_csv_path):
    with open(file1_path, "r") as file1:
        file1_lines = file1.readlines()

    with open(file2_path, "r") as file2:
        file2_lines = file2.readlines()

    max_lines = max(len(file1_lines), len(file2_lines))

    with open(output_csv_path, "w", newline="") as csv_file:
        writer = csv.writer(csv_file)

        # CSV header
        writer.writerow(["line", "file1_dataType", "file2_dataType"])

        for i in range(max_lines):
            line_number = i + 1

            if i < len(file1_lines):
                file1_type = file1_lines[i].strip()
            else:
                file1_type = "<missing line>"

            if i < len(file2_lines):
                file2_type = file2_lines[i].strip()
            else:
                file2_type = "<missing line>"

            # Only write rows where the data types are different
            if file1_type != file2_type:
                writer.writerow([line_number, file1_type, file2_type])

    print("Comparison CSV written to:", output_csv_path)


# Change these paths to your actual files
file1_path = "dataType_dict.txt"
file2_path = "dataType.txt"
output_csv_path = "datatype_dict-vs-auto.csv"

compare_type_files_to_csv(file1_path, file2_path, output_csv_path)