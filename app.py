from flask import Flask, request, render_template, redirect, url_for
import os
import subprocess
from threading import Thread

app = Flask(__name__)

# 디렉터리 설정
UPLOAD_FOLDER = 'uploads'
REF_FOLDER = 'ref'
OUTPUT_FOLDER = 'outputs'
CLADES_FOLDER = 'clades'
STATIC_FOLDER = 'static'  # 예시 파일을 저장할 static 디렉터리

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)
os.makedirs(CLADES_FOLDER, exist_ok=True)
os.makedirs(STATIC_FOLDER, exist_ok=True)  # static 디렉터리 생성 확인

# 작업 상태 관리
task_status = {"done": False, "results": [], "num_genomes": 0}

def run_fastani_task(saved_files):
    global task_status
    results = []

    for query_path in saved_files:
        ref_list_path = os.path.join(UPLOAD_FOLDER, 'ref_list.txt')
        with open(ref_list_path, 'w') as ref_list:
            for ref_file in os.listdir(REF_FOLDER):
                if ref_file.endswith('.fna'):
                    ref_list.write(os.path.join(REF_FOLDER, ref_file) + '\n')

        output_path = os.path.join(OUTPUT_FOLDER, f"{os.path.basename(query_path)}_output.txt")
        command = f"fastANI --query {query_path} --refList {ref_list_path} -o {output_path}"

        try:
            subprocess.run(command, shell=True, check=True)
            if os.path.exists(output_path):
                with open(output_path, 'r') as f:
                    for line in f:
                        results.append(line.strip())
            else:
                results.append(f"Error: Output file {output_path} not found.")
        except subprocess.CalledProcessError as e:
            results.append(f"Error during FastANI execution: {str(e)}")

    task_status["done"] = True
    task_status["results"] = results

@app.route('/')
def index():
    return render_template('index.html')  # index.html 템플릿 제공

@app.route('/fastani', methods=['POST'])
def fastani():
    global task_status
    task_status["done"] = False  # 작업 초기화

    # OUTPUT_FOLDER 초기화
    for file in os.listdir(OUTPUT_FOLDER):
        os.remove(os.path.join(OUTPUT_FOLDER, file))

    query_files = request.files.getlist('query')
    task_status["num_genomes"] = len(query_files)  # 업로드된 Genome 수 저장
    saved_files = []
    for query_file in query_files:
        saved_path = os.path.join(UPLOAD_FOLDER, query_file.filename)
        query_file.save(saved_path)  # 파일 저장
        saved_files.append(saved_path)

    # 별도의 스레드에서 FastANI 실행
    thread = Thread(target=run_fastani_task, args=(saved_files,))
    thread.start()

    estimated_time = len(query_files) * 1  # 1분 per Genome
    return render_template('waiting.html', message=f"Running SimpleAuris... Estimated time: {estimated_time} minute(s). Please wait.")

@app.route('/status', methods=['GET'])
def status():
    global task_status
    if task_status["done"]:
        return "done", 200
    return "processing", 202

@app.route('/results')
def results():
    global task_status
    return render_template('ani_results.html', results=task_status["results"])

@app.route('/clade', methods=['POST'])
def run_clade_analysis():
    global task_status
    clade_results = set()  # 중복 제거를 위해 set 사용
    query_files = [os.path.basename(f) for f in os.listdir(UPLOAD_FOLDER)]  # 업로드된 쿼리 파일 목록
    full_ani_results = task_status["results"]  # FastANI 전체 결과

    for filename in os.listdir(OUTPUT_FOLDER):
        if filename.endswith('_output.txt'):
            filepath = os.path.join(OUTPUT_FOLDER, filename)

            with open(filepath, 'r') as file:
                for line in file:
                    columns = line.strip().split()
                    if len(columns) < 3:
                        continue

                    try:
                        third_column = float(columns[2])
                    except ValueError:
                        continue

                    if third_column >= 99.8:  # ANI 값 기준 필터
                        first_column = columns[0]
                        second_column = os.path.basename(columns[1]).replace('.fna', '')
                        clade_results.add(f"{first_column}\t{second_column}\t{third_column}")

    clade_file = os.path.join(CLADES_FOLDER, 'clade_results.txt')
    with open(clade_file, 'w') as file:
        file.write("\n".join(clade_results))

    # 전체 ANI 결과와 클레이드 결과를 함께 전달
    return render_template(
        'clade_results.html',
        clade_results=sorted(clade_results),
        results=full_ani_results  # 전체 ANI 결과 전달
    )

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')

