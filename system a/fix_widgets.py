import json
import glob
import os

# Put your notebooks folder path here
folder = "."  # current folder — change if needed

notebooks = glob.glob(os.path.join(folder, "**/*.ipynb"), recursive=True)

if not notebooks:
    print("No .ipynb files found in this folder.")
else:
    for path in notebooks:
        with open(path, "r", encoding="utf-8") as f:
            nb = json.load(f)

        widgets = nb.get("metadata", {}).get("widgets", None)
        if widgets is not None and "state" not in widgets:
            nb["metadata"]["widgets"]["state"] = {}
            with open(path, "w", encoding="utf-8") as f:
                json.dump(nb, f, indent=1, ensure_ascii=False)
                f.write("\n")
            print(f"✅ Fixed: {path}")
        else:
            print(f"✔ Already fine: {path}")

    print("\nAll done! Now re-upload to GitHub.")
