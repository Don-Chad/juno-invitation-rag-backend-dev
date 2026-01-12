import os

def list_wav_files(name):
    # Construct the base directory path
    base_dir = os.path.join(
        "backchanneling",
        name
    )
    
    # List to store file paths and labels
    wav_files = []
    
    # Walk through the directory
    for root, _, files in os.walk(base_dir):
        for file in files:
            if file.endswith('.wav'):
                # Full path to the wav file
                file_path = os.path.join(root, file)
                # Convert to relative path
                relative_path = os.path.relpath(file_path, start=base_dir)
                # Label without the .wav extension
                label = os.path.splitext(file)[0]
                wav_files.append((relative_path, label))
    
    return wav_files

# Example usage
name = "tesla"
wav_files = list_wav_files(name)
for file_path, label in wav_files:
    print(f"File: {file_path}, Label: {label}")
