import json 
import os
import shutil


def dump_to_json(data, filename):

    os.makedirs(os.path.dirname(filename), exist_ok=True)

    with open(filename, 'w') as f:
        json.dump(data, f)
    print(f"Data has been written to {filename}")


def read_json_file(file_path):
    with open(file_path, 'r') as file:
        data = json.load(file)
    return data

def delete_directory_contents(directory):
    # Loop over all the items in the directory
    for filename in os.listdir(directory):
        file_path = os.path.join(directory, filename)
        try:
            # Check if it's a file or a directory
            if os.path.isfile(file_path) or os.path.islink(file_path):
                os.unlink(file_path)  # Delete the file or link
                
            elif os.path.isdir(file_path):
                shutil.rmtree(file_path)  # Delete the directory

        except Exception as e:
            print(f"Failed to delete {file_path}. Reason: {e}")
