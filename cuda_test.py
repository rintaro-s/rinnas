import openvino.runtime as ov

def check_npu_availability():
    # NPUデバイスのリストを取得
    available_devices = ov.Core().get_available_devices()
    
    # NPUが利用可能か確認
    if 'NPU' in available_devices:
        print("NPUは利用可能です。")
    else:
        print("NPUは利用できません。")

if __name__ == "__main__":
    check_npu_availability()
