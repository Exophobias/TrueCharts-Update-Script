# TrueCharts Repo Update Script

## Description

This Python script automates the process of updating your personal fork or clone of the [truecharts_archive](https://github.com/v3DJG6GL/truecharts_archive) with the latest changes from the [TrueCharts repository](https://github.com/truecharts/public). It compares charts between your personal repository and the master repository, updates versions, and optionally commits and pushes the changes back to your repository.

## Requirements

- Python 3.x
- See `requirements.txt` for required Python packages.

## Installation

1. **Clone the TrueCharts Master Repository:**

   You need to clone the official TrueCharts repository locally. This will serve as the source of the latest updates.

   ```bash
   git clone https://github.com/truecharts/public.git "C:/Github/TrueCharts Master"
   ```

2. **Fork truecharts_archive from v3DJG6GL:**

   Fork the [truecharts_archive from v3DJG6GL](https://github.com/v3DJG6GL/truecharts_archive) to your own GitHub account. This creates a personal copy of the repository where you can apply updates.

   - Visit the TrueCharts repository on GitHub.
   - Click on the "Fork" button in the upper right corner.

3. **Clone Your Forked Repository Locally:**

   Replace `yourusername` with your GitHub username.

   ```bash
   git clone https://github.com/yourusername/public.git "C:/Github/truecharts_archive"
   ```

4. **Clone this update script Repository:**

   You need to clone this repository locally. This will allow you to install requirements and easily update your other repos.

   ```bash
   git clone https://github.com/hey101/TrueCharts-Update-Script.git "C:/Github/TrueCharts Update Script"
   ```

5. **Navigate to the Repository Directory:**

   ```bash
   cd "C:/Github/TrueCharts Update Script"
   ```

6. **Install Required Packages:**

   ```bash
   pip install -r requirements.txt
   ```

## Configuration

Before running the script, you need to set up the configuration to match your environment.

1. **Copy the Example Configuration:**

   ```bash
   cp config.example.yaml config.yaml
   ```

2. **Edit `config.yaml`:**

   Open `config.yaml` in your favorite text editor and update the configuration options as needed. Main options to change are below:

   ```yaml
   repo:
     master_repo_path: "C:/Github/TrueCharts Master" # The local filesystem path to your cloned TrueCharts master repository. (https://github.com/truecharts/public)
     master_repo_branch: "master" # The branch to pull updates from in the master repository (usually `master`).
     personal_repo_path: "C:/Github/truecharts_archive" # The local filesystem path to your cloned personal repository (your personal fork of TrueCharts from https://github.com/v3DJG6GL/truecharts_archive)
     personal_repo_branch: "dev" # The branch to apply updates to in your personal repository.
   ```

   ### Configuration Options Explained

   - **repo:**
     - `master_repo_path`: The local filesystem path to your cloned TrueCharts master repository.
     - `master_repo_branch`: The branch to pull updates from in the master repository (usually `master`).
     - `personal_repo_path`: The local filesystem path to your cloned personal repository (your fork of TrueCharts).
     - `personal_repo_branch`: The branch to apply updates to in your personal repository.

   - **logging:**
     - `level`: Sets the logging verbosity. Options are `debug`, `info`, or `error`.
     - `log_to_file`: If `true`, logs will be written to a file specified in `log_file`.
     - `log_file`: The path to the log file where logs will be saved.

   - **git:**
     - `reset_type`: Determines how the script resets your local repository before pulling updates. Options:
       - `hard`: Resets the index and working tree. Any changes to tracked files in the working tree since the last commit are discarded.
       - `soft`: Does not touch the index file or the working tree at all, but resets the HEAD to the specified commit.
       - `none`: No reset is performed.
     - `clean_untracked`: If `true`, untracked files will be removed from the working tree.
     - `commit_after_finish`: Automatically commits changes after the script finishes updating.
     - `push_commit_after_finish`: Automatically pushes the committed changes to your personal repository.

   - **multiprocessing:**
     - `use_multiprocessing`: Enables multiprocessing for faster chart comparisons and updates. May not work on all systems.
     - `max_workers`: The number of worker processes to use. Set to `0` to use the number of CPU cores.

   - **folders_to_compare:**
     - A list of chart directories to compare and update between the master and personal repositories. Options include `stable`, `incubator`, `system`, and `premium`.

   - **update_README:**
     - If `true`, the script will update the `README.md` file in your personal repository with a changelog of updated apps.

   - **branches_to_run:**
     - A list of branches in your personal repository to process. The script will iterate over these branches and apply updates accordingly.

## Usage

Run the script using the following command:

```bash
python update.py
```

## Check the Results:

   - The script will update your personal repository with the latest charts.
   - If `commit_after_finish` and `push_commit_after_finish` are set to `true`, changes will be committed and pushed automatically.
   - Check `logs/update.log` for detailed logs if `log_to_file` is enabled.

## Notes

- **Forking and Cloning:**

  - **Forking** the TrueCharts repository allows you to have your own copy on GitHub where you can push changes.
  - **Cloning** your forked repository to your local machine lets you run the script and apply updates locally before pushing them back to GitHub.

- **Multiprocessing Compatibility:**

  - The multiprocessing feature may not work on all operating systems or hardware configurations. If you encounter issues, try setting `use_multiprocessing` to `false` in `config.yaml`.

- **Windows Users:**

  - Ensure that you have the `pywin32` package installed, as it is required for Windows-specific functionality in the script.

- **Logging:**

  - Adjust the `level` in the logging configuration to control the verbosity of the logs. For troubleshooting, setting it to `debug` can provide more detailed output.

## Troubleshooting

- **Script Exits Immediately:**

  - If the script exits immediately with a message about another instance running, ensure that no other instances are running. The script uses a mutex to prevent multiple instances from running simultaneously.

- **Git Errors:**

  - Ensure that the paths in `config.yaml` are correct and that you have the necessary permissions to access the repositories.
  - Check that the branches specified exist in the repositories.

- **Dependency Issues:**

  - Ensure all required Python packages are installed. Refer to the `requirements.txt` file.

## Contributing

Contributions are welcome! Please open an issue or submit a pull request on GitHub.