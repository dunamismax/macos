import subprocess


def run_command(command):
    """Run a shell command and print output in real-time."""
    process = subprocess.Popen(command, shell=True, executable="/bin/zsh")
    process.communicate()
    if process.returncode != 0:
        print(f"Command failed: {command}")
    else:
        print(f"Command succeeded: {command}")


def main():
    print("Setting up pyenv environment...")
    # Set up pyenv (simulate what you'd put in .zshrc)
    setup_pyenv = """
    export PYENV_ROOT="$HOME/.pyenv"
    export PATH="$PYENV_ROOT/bin:$PATH"
    eval "$(pyenv init - zsh)"
    """

    # Run everything in a single shell session
    full_command = f"""
    {setup_pyenv}
    pyenv shell 3.11.11 && pip install --upgrade open-webui
    """

    run_command(full_command)


if __name__ == "__main__":
    main()
