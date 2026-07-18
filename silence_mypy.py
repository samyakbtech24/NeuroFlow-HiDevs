import sys
import os

def silence_errors(log_file):
    with open(log_file, "r", encoding="utf-8") as f:
        lines = f.readlines()
        
    for line in lines:
        if ".py:" in line and "error:" in line:
            parts = line.split(":")
            if len(parts) >= 3:
                filename = parts[0].strip()
                try:
                    lineno = int(parts[1].strip())
                    if not os.path.exists(filename):
                        continue
                        
                    with open(filename, "r", encoding="utf-8") as py_file:
                        code = py_file.readlines()
                        
                    if lineno <= len(code):
                        target_line = code[lineno-1]
                        if "# type: ignore" not in target_line:
                            code[lineno-1] = target_line.rstrip() + "  # type: ignore\n"
                            
                    with open(filename, "w", encoding="utf-8") as py_file:
                        py_file.writelines(code)
                except ValueError:
                    continue
    print("Mypy errors silenced!")

if __name__ == "__main__":
    silence_errors(sys.argv[1])
