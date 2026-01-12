#!/usr/bin/env python3
import os
import sys
import argparse
import subprocess
from pathlib import Path
from datetime import datetime

class DeploymentError(Exception):
    pass

def check_ssh_connection(host, ssh_key_path):
    """Test SSH connection before proceeding"""
    try:
        result = subprocess.run(
            ['ssh', '-i', ssh_key_path, host, 'echo "SSH connection successful"'], 
            capture_output=True, 
            text=True, 
            timeout=10
        )
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        raise DeploymentError("SSH connection timed out")
    except Exception as e:
        raise DeploymentError(f"SSH connection failed: {str(e)}")

def check_remote_directory(host, remote_dir, ssh_key_path):
    """Check if remote directory exists and is not empty"""
    try:
        result = subprocess.run(
            ['ssh', '-i', ssh_key_path, host, f'[ -d "{remote_dir}" ] && [ "$(ls -A {remote_dir})" ]'],
            capture_output=True
        )
        return result.returncode == 0
    except Exception:
        return False

def create_backup(host, remote_dir, ssh_key_path):
    """Create backup of existing directory"""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_dir = f"{remote_dir}_backup_{timestamp}"
    subprocess.run(['ssh', '-i', ssh_key_path, host, f'cp -r {remote_dir} {backup_dir}'], check=True)
    return backup_dir

def read_gitignore(gitignore_path='.gitignore'):
    """Read .gitignore and return list of patterns"""
    if not os.path.exists(gitignore_path):
        print("Warning: .gitignore file not found")
        return []
    
    with open(gitignore_path, 'r') as f:
        patterns = [line.strip() for line in f if line.strip() and not line.startswith('#')]
    return patterns

def create_rsync_exclude_file(patterns):
    """Create temporary rsync exclude file from gitignore patterns"""
    additional_excludes = [
        ".git/",
        "__pycache__/",
        "onnx-models/",
        "recordings/",
        "root/",
        "samples/",
        "tmp/",
        "vdb_data/",
        "tools",
        "agents_old01",
        "agents_old02"


    ]
    patterns.extend(additional_excludes)
    
    with open('.rsync_exclude', 'w') as f:
        for pattern in patterns:
            f.write(f"{pattern}\n")
    return '.rsync_exclude'

def check_requirements_file():
    """Verify requirements.txt exists and is not empty"""
    if not os.path.exists('requirements.txt'):
        raise DeploymentError("requirements.txt not found")
    if os.path.getsize('requirements.txt') == 0:
        raise DeploymentError("requirements.txt is empty")

def find_available_worker_num(host, start_num, ssh_key_path):
    """Find the next available worker number starting from start_num"""
    current_num = start_num
    while True:
        worker_name = f"workerv{current_num}"
        remote_dir = f"/root/{worker_name}"
        if not check_remote_directory(host, remote_dir, ssh_key_path):
            return current_num
        current_num += 1

def deploy(worker_num=5, skip_requirements=False, force=False):
    """Deploy to worker server with safety checks"""
    if not 1 <= worker_num <= 100:
        raise DeploymentError("Worker number must be between 1 and 100")

    host = "root@64.23.171.50"
    ssh_key_path = os.path.expanduser('~/.ssh/id_ed25519_worker')

    print(f"Using SSH key: {ssh_key_path}")

    # Find next available worker number if current one exists
    actual_worker_num = find_available_worker_num(host, worker_num, ssh_key_path)
    if actual_worker_num != worker_num:
        print(f"\nℹ️ Worker {worker_num} exists, using worker {actual_worker_num} instead")
        worker_num = actual_worker_num

    worker_name = f"workerv{worker_num}"
    remote_dir = f"/root/{worker_name}"
    venv_name = f"venv_{worker_name}"

    print(f"\n🔍 Starting deployment process for {worker_name}")
    print("Performing safety checks...")

    # Test SSH connection
    if not check_ssh_connection(host, ssh_key_path):
        raise DeploymentError("Cannot establish SSH connection")

    # Check if remote directory exists and has content
    if check_remote_directory(host, remote_dir, ssh_key_path):
        if not force:
            response = input(f"\n⚠️  Warning: {remote_dir} already exists and contains files.\n"
                           f"Do you want to proceed? (This will create a backup)\n"
                           f"Type 'yes' to continue: ")
            if response.lower() != 'yes':
                print("Deployment cancelled.")
                return
        
        print("Creating backup of existing directory...")
        backup_dir = create_backup(host, remote_dir, ssh_key_path)
        print(f"Backup created at: {backup_dir}")

    # Create exclude file from gitignore
    exclude_file = create_rsync_exclude_file(read_gitignore())
    
    try:
        # Create remote directory
        subprocess.run(['ssh', '-i', ssh_key_path, host, f'mkdir -p {remote_dir}'], check=True)
        
        print("\n📤 Syncing files...")
        # Sync files using rsync with progress
        rsync_cmd = [
            'rsync',
            '-avz',
            '--progress',
            '--exclude-from=.rsync_exclude',
            '--delete',
            '-e', f'ssh -i {ssh_key_path}',
            '.',
            f'{host}:{remote_dir}'
        ]
        subprocess.run(rsync_cmd, check=True)
        
        # Always create venv and handle requirements unless explicitly skipped
        if not skip_requirements:
            print(f"\n🔧 Creating virtual environment: {venv_name}")
            # Remove existing venv if it exists
            subprocess.run(['ssh', '-i', ssh_key_path, host, f'rm -rf {remote_dir}/{venv_name}'], check=True)
            
            # Create and activate venv
            subprocess.run(['ssh', '-i', ssh_key_path, host, f'cd {remote_dir} && python3 -m venv {venv_name}'], check=True)
            
            # Verify requirements.txt
            check_requirements_file()
            
            print("📦 Installing requirements...")
            subprocess.run([
                'ssh', 
                '-i', ssh_key_path,
                host, 
                f'cd {remote_dir} && source {venv_name}/bin/activate && pip install -r requirements.txt'
            ], check=True)
            
        print(f"\n✅ Deployment to {worker_name} completed successfully!")
        if not skip_requirements:
            print(f"Virtual environment '{venv_name}' created and requirements installed")
        
    except subprocess.CalledProcessError as e:
        raise DeploymentError(f"Deployment failed: {str(e)}")
    finally:
        # Cleanup exclude file
        if os.path.exists('.rsync_exclude'):
            os.remove('.rsync_exclude')

def main():
    try:
        # Configure deployment options here
        worker_num = 8              # Worker number to deploy to
        skip_requirements = True   # Set to True to skip venv and requirements installation
        force = False               # Set to True to skip confirmation prompts
        
        deploy(worker_num, skip_requirements, force)
    except DeploymentError as e:
        print(f"\n❌ Error: {str(e)}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n\n🛑 Deployment cancelled by user")
        sys.exit(1)

if __name__ == '__main__':
    main()
