import subprocess
import sys
import tomllib


def run(cmd, desc, fix=False):
    print(f"\n{'🔧' if fix else '🧪'} {desc} ...")
    try:
        subprocess.run(cmd, check=True, shell=True)
    except subprocess.CalledProcessError as e:
        print(f"⚠️  {desc} failed ({e.returncode})")


def check_toml():
    try:
        with open("pyproject.toml", "rb") as f:
            tomllib.load(f)
        print("✅ TOML syntax OK")
    except Exception as e:
        print(f"❌ TOML error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    check_toml()
    run("toml-sort pyproject.toml --in-place --all", "Sorting TOML", fix=True)
    run("python -m black .", "Black formatting", fix=True)
    run("ruff check .", "Ruff lint")
    run("mypy src/opmed", "Mypy type check")
    print("\n🏁 Local check completed.")
