import copy
import json
import logging
import multiprocessing
import os
import shutil
import sys
import time
import inspect
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from tzlocal import get_localzone
from multiprocessing import Pool
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import git
from ruamel.yaml import YAML
from ruamel.yaml.scalarstring import DoubleQuotedScalarString
from tqdm import tqdm

from config import Config

config = Config()

def git_reset_and_pull(repo_path: Path, branch: str = 'main') -> None:  
    """
    Resets the git repository to the specified branch and pulls the latest changes.
    
    Resets the repository based on the reset type (hard, soft) and optionally cleans untracked files.

    Args:
        repo_path (str or Path): The path to the git repository.
        branch (str): The branch to reset and pull from.

    Raises:
        Exception: If there is an error with git operations.
    """
    try:
        repo = git.Repo(repo_path)
        if repo.active_branch.name != branch:
            repo.git.checkout(branch)
        if config.reset_type == 'hard':
            repo.git.reset('--hard')
        elif config.reset_type == 'soft':
            repo.git.reset('--soft')
        if config.clean_untracked:
            repo.git.clean('-fdx')
        repo.remotes.origin.pull(branch)
        logging.info(f"Reset and pulled latest changes for {repo_path} on branch {branch}")
    except Exception as e:
        logging.error(f"Error pulling repository at {repo_path} on branch {branch}: {e}")
        raise  # Re-raise the exception to stop the script

def git_commit_changes(repo_path: Path, current_time: str, changelog_entry: str) -> None:
    """
    Commits changes to the git repository without pushing.

    Args:
        repo_path (str or Path): The path to the git repository.
        current_time (str): The current timestamp to include in the commit message.
        changelog_entry (str): The changelog entry to include in the commit message.
    """
    repo = git.Repo(repo_path)
    try:
        # Stage all changes
        repo.git.add(A=True)

        # Create the commit message
        commit_title = f"Automatic Update {current_time}"
        commit_message = f"{commit_title}\n\n{changelog_entry}"

        # Commit the changes
        repo.index.commit(commit_message)
        logging.info(f"Changes committed locally with title: {commit_title}")
    except Exception as e:
        logging.error(f"Error committing changes: {e}")

def git_push_changes(repo_path: Path) -> None:
    """
    Pushes committed changes to the remote repository.

    Args:
        repo_path (str or Path): The path to the git repository.
    """
    try:
        repo = git.Repo(repo_path)
        # Add a delay to ensure file system operations are done
        time.sleep(2)
        origin = repo.remotes.origin
        origin.push(config.personal_repo_branch)
        logging.info(f"Changes pushed to branch {config.personal_repo_branch}.")
    except Exception as e:
        logging.error(f"Error pushing changes: {e}")

def get_folders_from_path(repo_path: Path, folder_name: str) -> set:
    """
    Retrieves the folder paths within a specified directory (e.g., stable, incubator).
    
    Args:
        repo_path (str or Path): The base path to the repository.
        folder_name (str): The name of the folder to retrieve subdirectories from.

    Returns:
        set: A set of paths representing subdirectories.
    """
    return set((repo_path / folder_name).iterdir())

def get_app_version_from_chart(chart_yaml_path: Path) -> Optional[str]:
    """ 
    Retrieves the app version from a Chart.yaml file.
    
    Args:
        chart_yaml_path (Path): The path to the Chart.yaml file.

    Returns:
        str: The app version found in the Chart.yaml, or None if an error occurs.
    """
    try:
        with chart_yaml_path.open('r', encoding='utf-8') as stream:
            chart_data = YAML().load(stream)
            return chart_data.get('appVersion')
    except Exception as e:
        logging.error(f"Error reading {chart_yaml_path}: {e}")
        return None

def save_app_versions_data(app_versions_json_path: Path, app_versions_data: Dict[str, Any]) -> None:
    """
    Saves the app versions data to a JSON file.
    
    Args:
        app_versions_json_path (Path): The path to the app_versions.json file.
        app_versions_data (dict): The app versions data to be saved.

    Raises:
        Exception: If there is an error writing to the JSON file.
    """
    try:
        with app_versions_json_path.open('w', encoding='utf-8') as f:
            json.dump(app_versions_data, f, indent=4)
            f.flush()  # Flush the buffer
            os.fsync(f.fileno())  # Ensure the file is written to disk
    except Exception as e:
        logging.error(f"Error writing to {app_versions_json_path}: {e}")

def get_app_versions_data(app_versions_json_path: Path) -> Optional[Dict[str, Any]]:
    """
    Loads the app versions data from a JSON file.

    Args:
        app_versions_json_path (Path): The path to the app_versions.json file.

    Returns:
        dict: The app versions data, or None if an error occurs.
    """
    try:
        with app_versions_json_path.open('r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logging.error(f"Error reading {app_versions_json_path}: {e}")
        return None

def increment_chart_version(old_chart_version: str) -> str:
    """
    Increments the chart version following semantic versioning rules.

    The function increments the patch version by 1. If the patch version reaches 10,
    it resets to 0 and increments the minor version by 1.

    Example:
        '1.0.9' -> '1.1.0'
        '1.0.0' -> '1.0.1'

    Args:
        old_chart_version (str): The current version of the chart in 'MAJOR.MINOR.PATCH' format.

    Returns:
        str: The incremented chart version.
    """
    version_parts = list(map(int, old_chart_version.split('.')))
    version_parts[2] = version_parts[2] + 1 if version_parts[2] < 9 else 0
    version_parts[1] = version_parts[1] + 1 if version_parts[2] == 0 else version_parts[1]
    return '.'.join(map(str, version_parts))

def get_old_and_new_chart_version(app_versions_data: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    """
    Retrieves the old and new chart versions by incrementing the current chart version.
    
    Args:
        app_versions_data (dict): The app versions data with chart version information.

    Returns:
        tuple: A tuple containing the old and new chart versions.
    """
    try:
        old_chart_version = sorted(app_versions_data.keys(), key=lambda v: [int(x) for x in v.split('.')])[-1]
        new_chart_version = increment_chart_version(old_chart_version)
        return old_chart_version, new_chart_version
    except Exception as e:
        logging.error(f"Error finding latest version in app_versions_data: {e}")
        return None, None

def update_app_versions_json(
    chart_name: str,
    old_chart_version: str,
    new_chart_version: str,
    old_app_version: str,
    new_app_version: str,
    app_versions_data: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Updates the app versions JSON with new chart and app versions.
    
    Args:
        chart_name (str): The name of the chart.
        old_chart_version (str): The current chart version.
        new_chart_version (str): The new chart version.
        old_app_version (str): The current app version.
        new_app_version (str): The new app version.
        app_versions_data (dict): The app versions data to update.

    Returns:
        dict: The updated app versions data.
    """
    # Step 1: Copy old chart version data to create new chart version data
    old_chart_version_data = copy.deepcopy(app_versions_data[old_chart_version])
    
    # Step 2: Update 'last_update' field for the new chart version
    old_chart_version_data['last_update'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    # Step 3: Replace all instances of the old chart and app version in the new chart data
    old_chart_version_data = replace_versions_in_data(old_chart_version_data, old_chart_version, new_chart_version, old_app_version, new_app_version)

    # Step 4: Insert new chart version at the top of the dictionary
    app_versions_data = {new_chart_version: old_chart_version_data, **app_versions_data}
    
    return app_versions_data

def replace_versions_in_data(
    data: Any,
    old_chart_version: str,
    new_chart_version: str,
    old_app_version: str,
    new_app_version: str
) -> Any:
    """
    Recursively replaces old chart and app versions with new versions in the data.

    This function walks through nested dictionaries and lists, replacing all occurrences
    of the old chart version and old app version with the new ones.

    Args:
        data (dict, list, or str): The data structure to update.
        old_chart_version (str): The old chart version to replace.
        new_chart_version (str): The new chart version.
        old_app_version (str): The old app version to replace.
        new_app_version (str): The new app version.

    Returns:
        The updated data with the new versions.
    """
    if isinstance(data, dict):
        return {
            key: replace_versions_in_data(value, old_chart_version, new_chart_version, old_app_version, new_app_version)
            for key, value in data.items()
        }
    elif isinstance(data, list):
        return [replace_versions_in_data(item, old_chart_version, new_chart_version, old_app_version, new_app_version) for item in data]
    elif isinstance(data, str):
        # Replace old chart version and app version with the new ones
        data = data.replace(old_chart_version, new_chart_version).replace(old_app_version, new_app_version)
        return data
    else:
        return data

def update_ix_values_from_master(
    chart_name: str,
    old_chart_version: str,
    new_chart_version: str,
    folder: str
) -> None:
    """
    Updates the ix_values.yaml file from the master values.yaml file for the given chart.

    Args:
        chart_name (str): The name of the chart.
        old_chart_version (str): The current chart version.
        new_chart_version (str): The new chart version.
        folder (str): The folder containing the chart.

    Raises:
        Exception: If an error occurs while updating the ix_values.yaml file.
    """
    ix_values_yaml_path = config.personal_repo_path / folder / chart_name / new_chart_version / 'ix_values.yaml'
    master_values_yaml_path = config.master_repo_path / 'charts' / folder / chart_name / 'values.yaml'
    if not ix_values_yaml_path.exists() or not master_values_yaml_path.exists():
        logging.error(f"Missing ix_values.yaml or values.yaml for {chart_name} in {folder}")
        return
    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.width = 1000000
    try:
        with master_values_yaml_path.open('r', encoding='utf-8') as f:
            master_values = yaml.load(f)
        with ix_values_yaml_path.open('r', encoding='utf-8') as f:
            ix_values = yaml.load(f)
        image_data = master_values.get('image', {})
        if 'image' in ix_values:
            ix_values['image']['repository'] = image_data.get('repository', ix_values['image'].get('repository'))
            ix_values['image']['tag'] = image_data.get('tag', ix_values['image'].get('tag'))
            ix_values['image']['pullPolicy'] = image_data.get('pullPolicy', ix_values['image'].get('pullPolicy'))
        with ix_values_yaml_path.open('w', encoding='utf-8') as f:
            yaml.dump(ix_values, f)
    except Exception as e:
        logging.error(f"Error updating ix_values.yaml for {chart_name} in {folder}: {e}")

def duplicate_and_rename_version_folder(
    chart_name: str,
    old_chart_version: str,
    new_chart_version: str,
    new_app_version: str,
    folder: str
) -> None:
    """
    Duplicates and renames the chart version folder for the given chart.

    Args:
        chart_name (str): The name of the chart.
        old_chart_version (str): The current chart version.
        new_chart_version (str): The new chart version.
        new_app_version (str): The new app version.
        folder (str): The folder containing the chart.

    Raises:
        Exception: If an error occurs while duplicating or renaming the folder.
    """
    old_version_folder_path = config.personal_repo_path / folder / chart_name / old_chart_version
    new_version_folder_path = config.personal_repo_path / folder / chart_name / new_chart_version
    
    if old_version_folder_path.exists() and not new_version_folder_path.exists():
        try:
            shutil.copytree(old_version_folder_path, new_version_folder_path)
            for root, dirs, files in os.walk(new_version_folder_path):
                for file in files:
                    file_path = os.path.join(root, file)
                    with open(file_path, 'a'):
                        os.fsync(os.open(file_path, os.O_RDWR))
            update_ix_values_from_master(chart_name, old_chart_version, new_chart_version, folder)
            update_chart_yaml(chart_name, new_chart_version, new_app_version, folder)
        except Exception as e:
            logging.error(f"Error duplicating folder {old_chart_version} for {chart_name} in {folder}: {e}")
    else:
        logging.debug(f"Folder for version {old_chart_version} not found or new version already exists for {chart_name} in {folder}.")

def update_chart_yaml(
    chart_name: str,
    new_chart_version: str,
    new_app_version: str,
    folder: str
) -> None:
    """
    Updates the version and appVersion fields in the Chart.yaml file.

    Args:
        chart_name (str): The name of the chart.
        new_chart_version (str): The new chart version.
        new_app_version (str): The new app version.
        folder (str): The folder containing the chart.

    Raises:
        Exception: If an error occurs while updating the Chart.yaml file.
    """
    chart_yaml_path = config.personal_repo_path / folder / chart_name / new_chart_version / 'Chart.yaml'
    yaml = YAML()
    yaml.preserve_quotes = True  
    try:
        with chart_yaml_path.open('r', encoding='utf-8') as f:
            chart_data = yaml.load(f)
        chart_data['version'] = new_chart_version
        chart_data['appVersion'] = new_app_version
        with chart_yaml_path.open('w', encoding='utf-8') as f:
            yaml.dump(chart_data, f)
        logging.info(f"Updated {chart_yaml_path} with version={new_chart_version} and appVersion={new_app_version}")
    except Exception as e:
        logging.error(f"Error updating Chart.yaml for {chart_yaml_path}: {e}")

def apply_custom_ix_values_overrides(ix_values_yaml_path: Path, custom_config: Dict[str, Any]) -> None:
    """
    Applies arbitrary custom overrides to ix_values.yaml based on the custom_config dictionary.
    custom_config can have an 'app_version' key plus any number of other keys (like 'image', 'mlImage', etc.).
    Each of these keys (except app_version) corresponds to a section in ix_values.yaml to override.

    :param ix_values_yaml_path: Path to the ix_values.yaml file
    :param custom_config: Dictionary from custom_images[chart_name], e.g.:
        {
          "app_version": "1.122.2",
          "image": {
            "repository": "ghcr.io/immich-app/immich-server",
            "tag": "v1.122.2@sha256:...",
            "pullPolicy": "IfNotPresent"
          },
          "mlImage": {
            "repository": ...,
            "tag": ...,
            "pullPolicy": ...
          },
          ...
        }

    For each key except 'app_version', we overlay the dictionary onto ix_values.yaml.
    """
    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.width = 1000000
    with ix_values_yaml_path.open('r', encoding='utf-8') as f:
        ix_values = yaml.load(f) or {}

    for key, value in custom_config.items():
        if key == 'app_version':
            # app_version handled separately by setting master_app_version = custom_app_version
            continue
        
        # Assume each key is a dictionary of fields to override in ix_values
        if isinstance(value, dict):
            # Ensure the key exists in ix_values
            if key not in ix_values:
                ix_values[key] = {}
            # Overwrite each field
            for subkey, subval in value.items():
                ix_values[key][subkey] = subval
        else:
            # If it's not a dict, let's store it as a string (uncommon case)
            ix_values[key] = value

    with ix_values_yaml_path.open('w', encoding='utf-8') as f:
        yaml.dump(ix_values, f)

def worker_init() -> None:
    """
    Initializes logging in child processes for multiprocessing.

    This function is called by each worker process when using multiprocessing.
    It configures the logging settings to ensure that logs from child processes
    are handled correctly.
    """
    # Remove existing handlers
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)
    # Set up logging
    log_level = getattr(logging, config.log_level, logging.ERROR)
    if config.log_to_file:
        config.log_file.parent.mkdir(parents=True, exist_ok=True)
        logging.basicConfig(
            level=log_level,
            format='%(asctime)s - %(levelname)s - %(message)s',
            filename=str(config.log_file)
        )
    else:
        logging.basicConfig(level=log_level, format='%(asctime)s - %(levelname)s - %(message)s')

def normalize_version_string(version: str) -> str:
    """Normalize version string by ensuring consistent format."""
    version = version.lower().strip()
    # Remove 'v' prefix if present
    if version.startswith('v'):
        version = version[1:]
    return version

def get_image_tag_parts(tag: str) -> Tuple[str, Optional[str]]:
    """
    Splits an image tag into version and SHA256 hash parts.
    
    Args:
        tag (str): The image tag string (e.g., 'v1.0.0@sha256:abc123...' or 'develop@sha256:xyz789...')
    
    Returns:
        tuple: (version, sha256_hash) where sha256_hash might be None
    """
    if '@sha256:' in tag:
        version, sha = tag.split('@sha256:', 1)
        return version, sha
    return tag, None

def compare_versions(version1: str, version2: str) -> int:
    """
    Compares two version strings, including build identifiers and SHA256 hashes.
    Returns: 
        1 if version1 > version2
        -1 if version1 < version2
        0 if equal
    """
    # Split version and hash for both strings
    v1, sha1 = get_image_tag_parts(version1)
    v2, sha2 = get_image_tag_parts(version2)
    
    # Normalize both versions
    v1 = normalize_version_string(v1)
    v2 = normalize_version_string(v2)
    
    # If versions are identical, check SHA256 hashes
    if v1 == v2:
        # If both have different SHA256 hashes, consider it an update
        if sha1 is not None and sha2 is not None and sha1 != sha2:
            return 1
        # If only one has a SHA256 hash, prefer the one with the hash
        if sha1 is not None and sha2 is None:
            return 1
        if sha1 is None and sha2 is not None:
            return -1
        return 0
        
    # Handle special versions
    special_versions = {'latest', 'stable', 'master', 'rolling', 'develop', 'dev', 'development', 'nightly'}
    if v1 in special_versions or v2 in special_versions:
        # If both are special versions and different, compare SHA256 hashes
        if v1 in special_versions and v2 in special_versions and v1 == v2:
            if sha1 is not None and sha2 is not None and sha1 != sha2:
                return 1
        return 0
    
    try:
        # Split into version and build parts
        v1_parts = v1.split('-')
        v2_parts = v2.split('-')
        
        # Compare main version numbers first
        v1_nums = [int(''.join(filter(str.isdigit, x))) for x in v1_parts[0].split('.')]
        v2_nums = [int(''.join(filter(str.isdigit, x))) for x in v2_parts[0].split('.')]
        
        # Pad with zeros if needed
        while len(v1_nums) < 3: v1_nums.append(0)
        while len(v2_nums) < 3: v2_nums.append(0)
        
        # Compare version numbers
        for i in range(max(len(v1_nums), len(v2_nums))):
            n1 = v1_nums[i] if i < len(v1_nums) else 0
            n2 = v2_nums[i] if i < len(v2_nums) else 0
            if n1 > n2: return 1
            if n1 < n2: return -1
            
        # If version numbers are equal, compare build identifiers if present
        if len(v1_parts) > 1 and len(v2_parts) > 1:
            # Both have build identifiers - compare them
            return 0 if v1_parts[1] == v2_parts[1] else 1 if v1_parts[1] > v2_parts[1] else -1
        elif len(v1_parts) > 1:
            return 1  # First version has build identifier, second doesn't
        elif len(v2_parts) > 1:
            return -1  # Second version has build identifier, first doesn't
            
        return 0  # Everything is equal
    except (ValueError, IndexError):
        # If parsing fails, compare as strings
        return 0 if v1 == v2 else 1 if v1 > v2 else -1

def compare_image_data(current_image: Dict[str, str], new_image: Dict[str, str]) -> bool:
    """
    Compares current and new image data to detect changes.
    
    Args:
        current_image (dict): Current image configuration
        new_image (dict): New image configuration
    
    Returns:
        bool: True if changes detected, False otherwise
    """
    # Debug logging for image comparison
    chart_name = "unknown"
    for frame in inspect.stack():
        args = inspect.getargvalues(frame[0]).locals
        if 'chart_name' in args:
            chart_name = args['chart_name']
            break
            
    logging.debug(f"Comparing images for {chart_name}")
    logging.debug(f"Current image: {current_image}")
    logging.debug(f"New image: {new_image}")
    
    # Compare repository if present in both
    if ('repository' in current_image and 'repository' in new_image and 
        current_image['repository'] != new_image['repository']):
        logging.debug(f"Repository changed: {current_image['repository']} -> {new_image['repository']}")
        return True
    
    # Compare tags including SHA256 hashes
    if 'tag' in current_image and 'tag' in new_image:
        current_tag = current_image['tag']
        new_tag = new_image['tag']
        
        # Enhanced detection for SHA changes
        current_ver, current_sha = get_image_tag_parts(current_tag)
        new_ver, new_sha = get_image_tag_parts(new_tag)
        
        logging.debug(f"Current version: {current_ver}, SHA: {current_sha}")
        logging.debug(f"New version: {new_ver}, SHA: {new_sha}")
        
        # If SHA256 hashes differ, consider it a change regardless of version
        if current_sha != new_sha and current_sha is not None and new_sha is not None:
            logging.info(f"{chart_name}: SHA256 hash changed for version {current_ver}: {current_sha} -> {new_sha}")
            return True
            
        # If versions are different, it's a change
        if current_ver != new_ver:
            logging.debug(f"Version changed: {current_ver} -> {new_ver}")
            return True
            
    # Compare pullPolicy if present in both
    if ('pullPolicy' in current_image and 'pullPolicy' in new_image and 
        current_image['pullPolicy'] != new_image['pullPolicy']):
        logging.debug(f"Pull policy changed: {current_image['pullPolicy']} -> {new_image['pullPolicy']}")
        return True
            
    logging.debug(f"No changes detected for {chart_name}")
    return False

def compare_and_update_chart(chart_name: str, folder: str) -> Optional[Dict[str, Any]]:
    """
    Compares the master and personal chart versions and updates if necessary.

    Args:
        chart_name (str): The name of the chart.
        folder (str): The folder containing the chart.

    Returns:
        dict: A dictionary with chart update details if an update occurs, None otherwise.
    """
    master_chart_yaml_path = config.master_repo_path / 'charts' / folder / chart_name / 'Chart.yaml'
    personal_app_versions_json_path = config.personal_repo_path / folder / chart_name / 'app_versions.json'
    
    # Check if this chart has custom image configuration
    has_custom_config = chart_name in config.custom_images
    
    # Special handling for charts with custom config that might be missing from master repo
    if has_custom_config and not master_chart_yaml_path.exists() and personal_app_versions_json_path.exists():
        logging.info(f"{chart_name} not found in master repo but has custom config - processing anyway")
        custom_image = config.custom_images.get(chart_name)
        custom_app_version = custom_image.get('app_version', 'latest')
        
        app_versions_data = get_app_versions_data(personal_app_versions_json_path)
        if not app_versions_data:
            logging.error(f"Could not retrieve app_versions_data for {chart_name} in {folder}")
            return None
        
        personal_app_version = app_versions_data[next(iter(app_versions_data))]["chart_metadata"].get("appVersion")
        if not personal_app_version:
            logging.error(f"Could not retrieve personal appVersion for {chart_name} in {folder}")
            return None
            
        latest_chart_data = app_versions_data[next(iter(app_versions_data))]
        latest_chart_version = latest_chart_data.get("version")
        
        # Check for image changes in custom config
        custom_image_differs = False
        old_sha = None
        new_sha = None
        
        if latest_chart_version:
            ix_values_yaml_path = config.personal_repo_path / folder / chart_name / latest_chart_version / 'ix_values.yaml'
            if ix_values_yaml_path.exists():
                yaml = YAML()
                yaml.preserve_quotes = True
                with ix_values_yaml_path.open('r', encoding='utf-8') as f:
                    ix_values = yaml.load(f) or {}
                
                # Compare current image with custom image
                current_image = ix_values.get('image', {})
                new_image = custom_image.get('image', {})
                
                # Compare tags with special attention to SHA256 changes
                if 'tag' in current_image and 'tag' in new_image:
                    current_tag = current_image.get('tag', '')
                    new_tag = new_image.get('tag', '')
                    current_ver, current_sha = get_image_tag_parts(current_tag)
                    new_ver, new_sha = get_image_tag_parts(new_tag)
                    old_sha = current_sha
                    
                    # Force update if SHA has changed, even if version is the same
                    if current_sha != new_sha and current_sha is not None and new_sha is not None:
                        logging.info(f"{chart_name} - SHA256 hash change detected: {current_sha} -> {new_sha}")
                        custom_image_differs = True
                    elif current_ver != new_ver:
                        logging.info(f"{chart_name} - Version change detected: {current_ver} -> {new_ver}")
                        custom_image_differs = True
                
                # Check repository changes too
                if ('repository' in current_image and 'repository' in new_image and 
                    current_image['repository'] != new_image['repository']):
                    logging.info(f"{chart_name} - Repository change detected: {current_image['repository']} -> {new_image['repository']}")
                    custom_image_differs = True
                
                # Check other custom config options
                if not custom_image_differs:
                    for key, value in custom_image.items():
                        if key in ('app_version', 'image'):
                            continue
                        if isinstance(value, dict):
                            current_section = ix_values.get(key, {})
                            for subkey, subval in value.items():
                                current_val = current_section.get(subkey, '')
                                if str(current_val) != str(subval):
                                    logging.info(f"{chart_name} - Custom config change in {key}.{subkey}: {current_val} -> {subval}")
                                    custom_image_differs = True
                                    break
                        else:
                            current_val = ix_values.get(key, '')
                            if str(current_val) != str(value):
                                logging.info(f"{chart_name} - Custom config change in {key}: {current_val} -> {value}")
                                custom_image_differs = True
                                break
                        if custom_image_differs:
                            break
        
        # If custom image differs or app version has changed, update the chart
        needs_update = custom_image_differs or (normalize_version_string(custom_app_version) != normalize_version_string(personal_app_version))
        logging.info(f"{chart_name} - Custom-only update needed: {needs_update}")
        
        if needs_update:
            old_chart_version, new_chart_version = get_old_and_new_chart_version(app_versions_data)
            if old_chart_version and new_chart_version:
                logging.info(f"{chart_name} in {folder}: Updating from {old_chart_version} to {new_chart_version}")
                app_versions_data = update_app_versions_json(
                    chart_name, old_chart_version, new_chart_version, personal_app_version, custom_app_version, app_versions_data
                )
                save_app_versions_data(personal_app_versions_json_path, app_versions_data)
                duplicate_and_rename_version_folder(chart_name, old_chart_version, new_chart_version, custom_app_version, folder)

                # Apply custom image configuration
                new_ix_values_yaml = config.personal_repo_path / folder / chart_name / new_chart_version / 'ix_values.yaml'
                logging.info(f"{chart_name} - Applying custom image overrides to {new_ix_values_yaml}")
                apply_custom_ix_values_overrides(new_ix_values_yaml, custom_image)

                return {
                    "chart_name": chart_name,
                    "folder": folder,
                    "master_app_version": custom_app_version,
                    "personal_app_version": personal_app_version,
                    "old_chart_version": old_chart_version,
                    "new_chart_version": new_chart_version,
                    "old_sha": old_sha,
                    "new_sha": new_sha
                }
        
        return None
            
    # Standard case - chart exists in both repos
    elif master_chart_yaml_path.exists() and personal_app_versions_json_path.exists():
        master_app_version = get_app_version_from_chart(master_chart_yaml_path)
        if not master_app_version:
            logging.error(f"Could not retrieve master appVersion for {chart_name} in {folder}")
            return None
        
        app_versions_data = get_app_versions_data(personal_app_versions_json_path)
        if not app_versions_data:
            logging.error(f"Could not retrieve app_versions_data for {chart_name} in {folder}")
            return None
            
        personal_app_version = app_versions_data[next(iter(app_versions_data))]["chart_metadata"].get("appVersion")
        if not personal_app_version:
            logging.error(f"Could not retrieve personal appVersion for {chart_name} in {folder}")
            return None
           
        # Check if the chart has custom configuration in config.yaml
        if has_custom_config:
            custom_app_version = config.custom_images.get(chart_name, {}).get('app_version')
            if custom_app_version:
                logging.info(f"Found custom app version for {chart_name}: {custom_app_version}")
                master_app_version = custom_app_version
                
        needs_update = False
        old_sha = None
        new_sha = None
                
        # Handle SHA256 updates for custom images
        if has_custom_config:
            custom_image = config.custom_images.get(chart_name)
            latest_chart_version = next(iter(app_versions_data))
            ix_values_yaml_path = config.personal_repo_path / folder / chart_name / latest_chart_version / 'ix_values.yaml'
            
            if ix_values_yaml_path.exists():
                yaml = YAML()
                yaml.preserve_quotes = True
                with ix_values_yaml_path.open('r', encoding='utf-8') as f:
                    ix_values = yaml.load(f) or {}
                
                current_image = ix_values.get('image', {})
                new_image = custom_image.get('image', {})
                
                # Detailed check for image changes
                if current_image and new_image:
                    # Use the compare_image_data function for detailed comparison
                    if compare_image_data(current_image, new_image):
                        # Get SHA details for changelog
                        if 'tag' in current_image and 'tag' in new_image:
                            current_tag = current_image.get('tag', '')
                            new_tag = new_image.get('tag', '')
                            _, current_sha = get_image_tag_parts(current_tag)
                            _, new_sha = get_image_tag_parts(new_tag)
                            old_sha = current_sha
                            needs_update = True
                            logging.info(f"{chart_name} - Image changes detected, needs update")
        
        # If we don't have a custom update yet, check for version differences
        if not needs_update:
            # Set needs_update to True if app versions are different
            if normalize_version_string(master_app_version) != normalize_version_string(personal_app_version):
                needs_update = True
                logging.info(f"{chart_name} needs update: {personal_app_version} -> {master_app_version}")
        
        if needs_update:
            old_chart_version, new_chart_version = get_old_and_new_chart_version(app_versions_data)
            if old_chart_version and new_chart_version:
                logging.info(f"{chart_name} in {folder}: Updating from {old_chart_version} to {new_chart_version}")
                app_versions_data = update_app_versions_json(
                    chart_name, old_chart_version, new_chart_version, personal_app_version, master_app_version, app_versions_data
                )
                save_app_versions_data(personal_app_versions_json_path, app_versions_data)
                duplicate_and_rename_version_folder(chart_name, old_chart_version, new_chart_version, master_app_version, folder)

                # Apply custom image configuration if this chart has overrides
                if has_custom_config:
                    new_ix_values_yaml = config.personal_repo_path / folder / chart_name / new_chart_version / 'ix_values.yaml'
                    apply_custom_ix_values_overrides(new_ix_values_yaml, config.custom_images[chart_name])

                return {
                    "chart_name": chart_name,
                    "folder": folder,
                    "master_app_version": master_app_version,
                    "personal_app_version": personal_app_version,
                    "old_chart_version": old_chart_version,
                    "new_chart_version": new_chart_version,
                    "old_sha": old_sha,
                    "new_sha": new_sha
                }
        else:
            logging.debug(f"{chart_name} in {folder} is up to date.")
    
    else:
        if not master_chart_yaml_path.exists() and personal_app_versions_json_path.exists():
            logging.debug(f"{chart_name}: Chart exists in personal repo but not in master repo and has no custom config.")
        elif master_chart_yaml_path.exists() and not personal_app_versions_json_path.exists():
            logging.debug(f"{chart_name}: Chart exists in master repo but not in personal repo.")
        else:
            logging.debug(f"{chart_name}: Files missing in both master and personal repositories in {folder}.")
    
    return None

def compare_and_update_chart_with_progress(chart_name: str, folder: str, progress_bar: tqdm) -> Optional[Dict[str, Any]]:
    """
    Compares and updates the chart while updating a progress bar.

    Args:
        chart_name (str): The name of the chart.
        folder (str): The folder containing the chart.
        progress_bar (tqdm): The progress bar to update during processing.

    Returns:
        dict: A dictionary with chart update details if an update occurs, None otherwise.
    """
    result = compare_and_update_chart(chart_name, folder)
    progress_bar.update(1)
    return result

def process_charts_in_parallel_with_progress(chart_names: List[str], folder: str) -> List[Dict[str, Any]]:
    """
    Processes charts in parallel with progress tracking in a specific folder.

    Args:
        chart_names (list): A list of chart names to process.
        folder (str): The folder containing the charts.

    Returns:
        list: A list of dictionaries containing chart update details.
    """
    differences = []
    total_folders = len(chart_names)
    is_pythonw = sys.executable.lower().endswith('pythonw.exe')
    disable_tqdm = is_pythonw or not sys.stdout.isatty()

    with tqdm(total=total_folders, desc=f"Processing Charts in {folder}", unit="chart", disable=disable_tqdm) as progress_bar:
        with ThreadPoolExecutor(max_workers=config.max_workers) as executor:
            futures = {
                executor.submit(compare_and_update_chart_with_progress, chart_name, folder, progress_bar): chart_name
                for chart_name in chart_names
            }
            for future in as_completed(futures):
                result = future.result()
                if result:
                    differences.append(result)
    return differences

def compare_and_update_chart_multiprocessing(args: Tuple[str, str]) -> Optional[Dict[str, Any]]:
    """
    Wrapper function to compare and update charts using multiprocessing.

    Args:
        args (tuple): A tuple containing the chart name and folder.

    Returns:
        dict: A dictionary with chart update details if an update occurs, None otherwise.
    """
    chart_name, folder = args
    try:
        return compare_and_update_chart(chart_name, folder)
    except Exception as e:
        logging.error(f"Error processing chart {chart_name} in folder {folder}: {e}")
        return None

def process_charts_in_parallel_multiprocessing(chart_names: List[str], folder: str) -> List[Dict[str, Any]]:
    """
    Processes charts in parallel using multiprocessing for faster performance.
    Args:
        chart_names (List[str]): A list of chart names to process.
        folder (str): The folder containing the charts.
    Returns:
        List[Dict[str, Any]]: A list of dictionaries containing chart update details.
    """
    differences = []
    total_folders = len(chart_names)
    is_pythonw = sys.executable.lower().endswith('pythonw.exe')
    disable_tqdm = is_pythonw or not sys.stdout.isatty()

    with Pool(processes=config.max_workers, initializer=worker_init) as pool:
        args = [(chart_name, folder) for chart_name in chart_names]
        for result in tqdm(pool.imap_unordered(compare_and_update_chart_multiprocessing, args), 
                            total=total_folders, 
                            desc=f"Processing Charts in {folder}", 
                            unit="chart",
                            disable=disable_tqdm):
            if result:
                differences.append(result)

    return differences

def update_catalog_json_in_memory(differences: List[Dict[str, Any]], catalog_data: Dict[str, Any]) -> None:
    """
    Updates the catalog JSON data in memory based on chart differences.
    Args:
        differences (List[Dict[str, Any]]): A list of dictionaries containing chart differences.
        catalog_data (dict): The current catalog data to update.
    """
    for diff in differences:
        folder = diff['folder']
        chart_name = diff['chart_name']
        master_app_version = diff['master_app_version']

        folder_data = catalog_data.setdefault(folder, {})
        
        chart_data = folder_data.setdefault(chart_name, {})

        latest_version = chart_data.get('latest_version', '0.0.0')
        new_latest_chart_version = increment_chart_version(latest_version)

        if chart_data:
            chart_data.update({
                'latest_version': new_latest_chart_version,
                'latest_app_version': master_app_version,
                'latest_human_version': f"{master_app_version}_{new_latest_chart_version}",
                'last_update': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            })

def save_catalog_json(catalog_data: Dict[str, Any], catalog_json_path: Path) -> None:
    """
    Saves the updated catalog data to the catalog.json file.
    Args:
        catalog_data (dict): The updated catalog data to save.
        catalog_json_path (Path): The path to the catalog.json file.
    Raises:
        Exception: If there is an error writing to the catalog.json file.
    """
    try:
        with catalog_json_path.open('w', encoding='utf-8') as f:
            json.dump(catalog_data, f, indent=4)
            f.flush()  # Flush the buffer
            os.fsync(f.fileno())  # Ensure the file is written to disk
        logging.info(f"catalog.json updated successfully.")
    except Exception as e:
        logging.error(f"Error writing to {catalog_json_path}: {e}")

def update_readme(changelog_entry: str) -> None:
    """
    Updates the README.md file with the given changelog entry.
    Args:
        changelog_entry (str): The changelog entry to add to the README.
    Raises:
        Exception: If there is an error updating the README file.
    """
    try:
        with config.readme_path.open('r', encoding='utf-8') as f:
            readme_content = f.read()
    except FileNotFoundError:
        readme_content = ""
    
    changelog_heading = "- ### Changelog:\n"
    
    if changelog_heading in readme_content:
        readme_content_parts = readme_content.split(changelog_heading, 1)
        new_readme_content = readme_content_parts[0] + changelog_entry + readme_content_parts[1]
    else:
        new_readme_content = readme_content + "\n" + changelog_entry
    
    try:
        with config.readme_path.open('w', encoding='utf-8') as f:
            f.write(new_readme_content)
            f.flush()
            os.fsync(f.fileno())
        logging.info(f"Updated README.md with the latest changelog.")
    except Exception as e:
        logging.error(f"Error writing to {config.readme_path}: {e}")

def generate_changelog_entry(differences: List[Dict[str, Any]]) -> Tuple[str, str]:
    """
    Generates a changelog entry string based on chart differences.
    Args:
        differences (List[Dict[str, Any]]): A list of dictionaries containing chart differences.
    Returns:
        Tuple[str, str]: A tuple containing the current timestamp and the formatted changelog entry string.
    """
    changelog_heading = "- ### Changelog:\n"
    local_timezone = get_localzone()
    current_time = datetime.now(local_timezone).strftime("%Y.%m.%d @ %I:%M %p %Z")
    changelog_entry = f"\t- {current_time}:\n"

    folder_differences = {}
    for diff in differences:
        folder = diff['folder']
        if folder not in folder_differences:
            folder_differences[folder] = []
        folder_differences[folder].append(diff)

    for folder in config.folders_to_compare:
        if folder in folder_differences:
            diffs_in_folder = folder_differences[folder]
            sorted_diffs = sorted(diffs_in_folder, key=lambda d: d['chart_name'].lower())
            changelog_entry += f"\t\t- {folder.capitalize()}:\n"
            for diff in sorted_diffs:
                chart_name = diff['chart_name']
                old_version = diff['personal_app_version']
                new_version = diff['master_app_version']
                
                special_versions = {'latest', 'stable', 'master', 'rolling', 'develop', 'dev', 'development', 'nightly'}
                
                # Check if app versions are the same but SHA256 changed
                if old_version == new_version and diff.get('old_sha') and diff.get('new_sha'):
                    old_sha = diff.get('old_sha', '')[-7:]
                    new_sha = diff.get('new_sha', '')[-7:]
                    old_str = old_sha if old_sha else old_version
                    new_str = new_sha if new_sha else new_version
                elif old_version.lower() in special_versions and new_version.lower() in special_versions:
                    old_sha = diff.get('old_sha', '')[-7:]
                    new_sha = diff.get('new_sha', '')[-7:]
                    old_str = old_sha if old_sha else old_version
                    new_str = new_sha if new_sha else new_version
                else:
                    old_str = f"v{old_version.lstrip('v')}" if old_version.lower() not in special_versions else old_version
                    new_str = f"v{new_version.lstrip('v')}" if new_version.lower() not in special_versions else new_version
                
                changelog_entry += f"\t\t\t- {chart_name}: {old_str} --> {new_str}\n"

    return current_time, changelog_heading + changelog_entry

def process_folders_in_parallel_with_progress(
    master_repo_path: Path,
    personal_repo_path: Path,
    folders: List[str]
) -> List[Dict[str, Any]]:  # Changed } to :
    all_differences = []
    for folder in folders:
        logging.debug(f"\nProcessing folder: {folder}")
        master_folders = get_folders_from_path(master_repo_path / 'charts', folder)
        personal_folders = get_folders_from_path(personal_repo_path, folder)

        master_folder_names = {folder.name for folder in master_folders}
        personal_folder_names = {folder.name for folder in personal_folders}
        all_folder_names = sorted(master_folder_names.union(personal_folder_names))

        if len(all_folder_names) == 0:
            logging.debug(f"No charts found in folder {folder}. Skipping.")
            continue

        differences = process_charts_in_parallel_with_progress(all_folder_names, folder)

        if differences:
            logging.info(f"\nTotal app version differences found in {folder}: {len(differences)}")
            all_differences.extend(differences)
            update_catalog_json_in_memory(differences, catalog_data)
            save_catalog_json(catalog_data, config.catalog_json_path)

    return all_differences

def process_folders_in_parallel_multiprocessing(
    master_repo_path: Path,
    personal_repo_path: Path,
    folders: List[str]
) -> List[Dict[str, Any]]:  # Changed } to :
    all_differences = []
    for folder in folders:
        logging.debug(f"\nProcessing folder: {folder}")
        master_folders = get_folders_from_path(master_repo_path / 'charts', folder)
        personal_folders = get_folders_from_path(personal_repo_path, folder)
        master_folder_names = {folder.name for folder in master_folders}
        personal_folder_names = {folder.name for folder in personal_folders}
        all_folder_names = sorted(master_folder_names.union(personal_folder_names))

        if len(all_folder_names) == 0:
            logging.debug(f"No charts found in folder {folder}. Skipping.")
            continue

        differences = process_charts_in_parallel_multiprocessing(all_folder_names, folder)

        if differences:
            logging.info(f"\nTotal app version differences found in {folder}: {len(differences)}")
            all_differences.extend(differences)
            update_catalog_json_in_memory(differences, catalog_data)
            save_catalog_json(catalog_data, config.catalog_json_path)

    return all_differences

if __name__ == "__main__":
    # Initialize logging and other setup
    try:
        import win32event
        import win32api
        import winerror
    except ImportError:
        logging.error("pywin32 is required for this script to run.")
        sys.exit(1)

    mutex_name = "Global\\TrueNasGithubUpdateScript"
    mutex = win32event.CreateMutex(None, False, mutex_name)
    last_error = win32api.GetLastError()

    if (last_error == winerror.ERROR_ALREADY_EXISTS):
        logging.error("Another instance is already running. Exiting.")
        sys.exit(0)

    multiprocessing.set_start_method('spawn', force=True)
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)

    log_level = getattr(logging, config.log_level, logging.ERROR)

    if config.log_to_file:
        config.log_file.parent.mkdir(parents=True, exist_ok=True)
        logging.basicConfig(level=log_level, format='%(asctime)s - %(levelname)s - %(message)s', filename=str(config.log_file))
    else:
        logging.basicConfig(level=log_level, format='%(asctime)s - %(levelname)s - %(message)s')

    for branch in config.branches_to_run:
        config.override_branch(branch)
        logging.info(f"Processing branch: {branch}")
        try:
            git_reset_and_pull(config.master_repo_path, branch=config.master_repo_branch)
            git_reset_and_pull(config.personal_repo_path, branch=config.personal_repo_branch)
        except Exception as e:
            logging.error(f"Terminating script due to git error: {e}")
            sys.exit(1)

        start_time = time.time()

        try:
            with config.catalog_json_path.open('r', encoding='utf-8') as f:
                catalog_data = json.load(f)
        except Exception as e:
            logging.error(f"Error reading {config.catalog_json_path}: {e}")
            catalog_data = {}

        if config.use_multiprocessing:
            logging.info("Running with multiprocessing")
            all_differences = process_folders_in_parallel_multiprocessing(config.master_repo_path, config.personal_repo_path, config.folders_to_compare)
        else:
            logging.info("Running without multiprocessing")
            all_differences = process_folders_in_parallel_with_progress(config.master_repo_path, config.personal_repo_path, config.folders_to_compare)

        if all_differences:
            sorted_differences = sorted(all_differences, key=lambda diff: diff['chart_name'])
            
            current_time, changelog_entry = generate_changelog_entry(sorted_differences)
            
            if config.update_readme_file:
                update_readme(changelog_entry)
            
            if config.commit_after_finish:
                git_commit_changes(config.personal_repo_path, current_time, changelog_entry)
                
                if config.push_commit_after_finish:
                    git_push_changes(config.personal_repo_path)
        else:
            logging.info("No differences found.")

        end_time = time.time()
        total_time = end_time - start_time
        logging.info(f"\nExecution time with max_workers={config.max_workers}: {total_time:.2f} seconds")