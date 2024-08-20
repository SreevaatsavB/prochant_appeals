import json 


def dump_to_json(data, filename):
    with open(filename, 'w') as f:
        json.dump(data, f)
    print(f"Data has been written to {filename}")

def read_json_file(file_path):
    with open(file_path, 'r') as file:
        data = json.load(file)
    return data