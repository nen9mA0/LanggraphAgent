import os
import subprocess

except_file_lst = [
    "codex_app_server_protocol.schemas.json",
    "codex_app_server_protocol.v2.schemas.json"
]

cur_dir = os.path.dirname(os.path.abspath(__file__))
output_dir = os.path.join(cur_dir, "..")

for file in os.listdir(cur_dir):
    if file in except_file_lst and file.endswith(".json"):
        input_filepath = os.path.join(cur_dir, file)
        output_filename = file.replace(".json", ".py")
        output_filepath = os.path.join(output_dir, output_filename)
        os.system("datamodel-codegen.exe --input %s --input-file-type jsonschema --output-model-type pydantic_v2.BaseModel --output %s" %(input_filepath, output_filepath))
        a = 0