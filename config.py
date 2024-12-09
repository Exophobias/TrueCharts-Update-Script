from pathlib import Path
import yaml
import os

class Config:
    def __init__(self, config_file='config.yaml'):
        self.config_file = Path(config_file)
        self.master_repo_path = None
        self.personal_repo_path = None
        self.master_repo_branch = None
        self.personal_repo_branch = None
        self.log_file = None
        self.log_level = None
        self.log_to_file = None
        self.catalog_json_path = None
        self.readme_path = None
        self.use_multiprocessing = None
        self.max_workers = None
        self.reset_type = None
        self.clean_untracked = None
        self.commit_after_finish = None
        self.push_commit_after_finish = None
        self.folders_to_compare = None
        self.update_readme_file = None
        self.branches_to_run = None  # Add branches_to_run attribute
        self.load_config()

    def load_config(self):
        if not self.config_file.exists():
            raise FileNotFoundError(f"{self.config_file} not found")
        with self.config_file.open('r', encoding='utf-8') as file:
            config = yaml.safe_load(file)
            self.master_repo_path = Path(config['repo'].get('master_repo_path'))
            self.master_repo_branch = config['repo'].get('master_repo_branch')
            self.personal_repo_path = Path(config['repo'].get('personal_repo_path'))
            self.personal_repo_branch = config['repo'].get('personal_repo_branch')
            self.log_file = Path(config['logging'].get('log_file', 'logs/script.log'))
            self.log_level = config['logging'].get('level', 'ERROR').upper()
            self.log_to_file = config['logging'].get('log_to_file', False)
            self.catalog_json_path = self.personal_repo_path / 'catalog.json'
            self.readme_path = self.personal_repo_path / 'README.md'

            self.use_multiprocessing = config['multiprocessing'].get('use_multiprocessing', True)
            self.max_workers = config['multiprocessing'].get('max_workers', os.cpu_count())
            if self.max_workers <= 0:
                self.max_workers = os.cpu_count()

            self.reset_type = config['git'].get('reset_type', 'hard')
            self.clean_untracked = config['git'].get('clean_untracked', True)
            self.commit_after_finish = config['git'].get('commit_after_finish', True)
            self.push_commit_after_finish = config['git'].get('push_commit_after_finish', True)

            self.folders_to_compare = config.get('folders_to_compare', ["stable", "incubator", "system", "premium"])
            self.update_readme_file = config.get('update_README', True)
            self.branches_to_run = config.get('branches_to_run', [self.personal_repo_path])

            # Load custom images configuration
            self.custom_images = config.get('custom_images', {})

    def override_branch(self, new_branch):
        self.personal_repo_branch = new_branch

    def save_config(self):
        config_data = {
            'repo': {
                'master_repo_path': str(self.master_repo_path),
                'master_repo_branch': self.master_repo_branch,
                'personal_repo_path': str(self.personal_repo_path),
                'personal_repo_branch': self.personal_repo_branch,
            },
            'logging': {
                'log_file': str(self.log_file),
                'level': self.log_level,
                'log_to_file': self.log_to_file,
            },
            'git': {
                'reset_type': self.reset_type,
                'clean_untracked': self.clean_untracked,
                'commit_after_finish': self.commit_after_finish,
                'push_commit_after_finish': self.push_commit_after_finish,
            },
            'multiprocessing': {
                'use_multiprocessing': self.use_multiprocessing,
                'max_workers': self.max_workers,
            },
            'folders_to_compare': self.folders_to_compare,
            'update_README': self.update_readme_file
        }

        with self.config_file.open('w', encoding='utf-8') as file:
            yaml.dump(config_data, file)