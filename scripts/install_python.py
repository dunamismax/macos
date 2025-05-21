import subprocess


def run_command(command):
    """Run a shell command and print output."""
    process = subprocess.run(command, shell=True, executable="/bin/zsh", text=True)
    if process.returncode != 0:
        print(f"Command failed: {command}")
    else:
        print(f"Command succeeded: {command}")


def main():
    print("Initializing pyenv environment...")

    # Set up pyenv environment like .zshrc would
    setup_pyenv = """
    export PYENV_ROOT="$HOME/.pyenv"
    export PATH="$PYENV_ROOT/bin:$PATH"
    eval "$(pyenv init --path)"
    eval "$(pyenv init - zsh)"
    """

    print("Fetching latest Python version from pyenv...")
    command = f"""
    {setup_pyenv}
    latest_version=$(pyenv install --list | grep -E '^\s*[0-9]+\\.[0-9]+\\.[0-9]+$' | tail -1 | tr -d ' ')
    echo "Latest Python version is: $latest_version"
    pyenv install --skip-existing $latest_version
    pyenv global $latest_version
    python --version
    """

    run_command(command)


if __name__ == "__main__":
    main()
