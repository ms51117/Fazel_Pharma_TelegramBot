import os

# لیست پوشه‌ها و فایل‌هایی که نباید خوانده شوند
IGNORE_DIRS = {'.git', '__pycache__', 'venv', 'env', '.idea', 'patient_files'}
IGNORE_FILES = {'bundler.py', 'fazel_pharma.db', '.DS_Store'}
# پسوندهایی که می‌خواهید بخوانید
ALLOWED_EXTENSIONS = {'.py', '.txt', '.md', '.env'}

output_file = "full_project_code.txt"

with open(output_file, "w", encoding="utf-8") as outfile:
    for root, dirs, files in os.walk("."):
        # حذف پوشه‌های غیرمجاز از جستجو
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]

        for file in files:
            if file in IGNORE_FILES:
                continue

            ext = os.path.splitext(file)[1]
            if ext in ALLOWED_EXTENSIONS:
                file_path = os.path.join(root, file)
                outfile.write(f"\n{'=' * 50}\n")
                outfile.write(f"FILE: {file_path}\n")
                outfile.write(f"{'=' * 50}\n\n")

                try:
                    with open(file_path, "r", encoding="utf-8") as infile:
                        outfile.write(infile.read())
                except Exception as e:
                    outfile.write(f"Error reading file: {e}")

                outfile.write("\n")

print(f"Done! All codes saved in {output_file}")
