"""
Blender script to rename armature bones to Unreal Engine standard naming convention.

Supports:
- VRM (hips, spine, chest, shoulder, upper_arm/lower_arm, upper_leg/lower_leg, toes, fingers)
- Mixamo (mixamorig:Hips, mixamorig:Spine*, mixamorig:Left/Right*, Hand/Toe/Head Ends)
- Rigify Human (spine, shoulder, upper_arm/forearm, thigh/shin, toe, palm, fingers)

For Mixamo, finger/toe/head end bones are deleted.
For VRM/Rigify/Unknown, unmapped bones are standardized (e.g., .L/.R -> _l/_r, .00x -> _0x, lowercase).
"""

# 操作步骤：选中骨骼进入编辑模式，将次脚本拖入Blender的脚本页面点击运行

# 需要选中骨骼在编辑模式下运行此脚本
# 支持骨骼类型: VRM / Rigify / Mixamo
# 注意：Mixamo骨骼会删除 头部/手指/脚趾 的_End末端骨骼

import bpy
import re

# --- 骨骼映射字典 ---
# VRM 基础映射
VRM_BASE_MAP = {
    "hips": "pelvis", "spine": "spine_01", "neck": "neck_01", "head": "head",
    "shoulder.L": "clavicle_l", "shoulder.R": "clavicle_r",
    "upper_arm.L": "upperarm_l", "upper_arm.R": "upperarm_r",
    "lower_arm.L": "lowerarm_l", "lower_arm.R": "lowerarm_r", 
    "hand.L": "hand_l", "hand.R": "hand_r",
    "upper_leg.L": "thigh_l", "upper_leg.R": "thigh_r", 
    "lower_leg.L": "calf_l", "lower_leg.R": "calf_r",
    "foot.L": "foot_l", "foot.R": "foot_r",
    "toes.L": "ball_l", "toes.R": "ball_r",
}

# Rigify 基础映射
RIGIFY_BASE_MAP = {
    "pelvis.L": "pelvis_l", "pelvis.R": "pelvis_r",
    "spine": "spine_01", "neck": "neck_01", "head": "head",
    "shoulder.L": "clavicle_l", "shoulder.R": "clavicle_r",
    "upper_arm.L": "upperarm_l", "upper_arm.R": "upperarm_r",
    "forearm.L": "lowerarm_l", "forearm.R": "lowerarm_r", # Rigify forearm -> UE lowerarm
    "hand.L": "hand_l", "hand.R": "hand_r",
    "thigh.L": "thigh_l", "thigh.R": "thigh_r",
    "shin.L": "calf_l", "shin.R": "calf_r",             # Rigify shin -> UE calf
    "foot.L": "foot_l", "foot.R": "foot_r",
    "toe.L": "ball_l", "toe.R": "ball_r",               # Rigify toe -> UE ball
    "palm.01.L": "index_metacarpal_l", "palm.02.L": "middle_metacarpal_l",
    "palm.03.L": "ring_metacarpal_l", "palm.04.L": "pinky_metacarpal_l",
    "palm.01.R": "index_metacarpal_r", "palm.02.R": "middle_metacarpal_r",
    "palm.03.R": "ring_metacarpal_r", "palm.04.R": "pinky_metacarpal_r",
}

# Mixamo 基础映射
MIXAMO_BASE_MAP = {
    "Hips": "pelvis",
    "Spine": "spine_01", "Spine1": "spine_02", "Spine2": "spine_03",
    "Neck": "neck_01", "Head": "head",
    "LeftShoulder": "clavicle_l", "RightShoulder": "clavicle_r",
    "LeftArm": "upperarm_l", "RightArm": "upperarm_r",
    "LeftForeArm": "lowerarm_l", "RightForeArm": "lowerarm_r",
    "LeftHand": "hand_l", "RightHand": "hand_r",
    "LeftUpLeg": "thigh_l", "RightUpLeg": "thigh_r",
    "LeftLeg": "calf_l", "RightLeg": "calf_r",
    "LeftFoot": "foot_l", "RightFoot": "foot_r",
    "LeftToeBase": "ball_l", "RightToeBase": "ball_r",
}

def get_bone_mapping_and_type(edit_bones):
    bone_names = set(edit_bones.keys()) # 使用 set 提高查找效率

    # 检测 Mixamo
    if any(name.startswith("mixamorig:") for name in bone_names):
        mapping = {}
        for original, target in MIXAMO_BASE_MAP.items():
            mapping[f"mixamorig:{original}"] = target
        # Mixamo 手指映射
        for finger_base, finger_ue_name in zip(["Thumb", "Index", "Middle", "Ring", "Pinky"], ["thumb", "index", "middle", "ring", "pinky"]):
            for i in range(1, 5):
                left_original = f"mixamorig:LeftHand{finger_base}{i}"
                right_original = f"mixamorig:RightHand{finger_base}{i}"
                if i <= 3:
                    mapping[left_original] = f"{finger_ue_name}_{i:02d}_l"
                    mapping[right_original] = f"{finger_ue_name}_{i:02d}_r"
        return "Mixamo", mapping

    # 检测 Rigify (优先检查 Rigify 特有骨骼)
    # 如果存在 Rigify 特有的骨骼名称 (如 spine.00x, palm.x, f_*, forearm, shin)，则认为是 Rigify
    # 这些名称在标准 VRM 中通常不存在
    rigify_specific_indicators = [
        lambda names: any(name.startswith("spine.") and name != "spine" for name in names), # 例如 spine.001
        lambda names: any(name.startswith("palm.") for name in names), # palm.01.L
        lambda names: any(name.startswith("f_") for name in names),   # f_index.01.L
        lambda names: "forearm.L" in names or "forearm.R" in names,   # Rigify 特有
        lambda names: "shin.L" in names or "shin.R" in names,         # Rigify 特有
    ]
    is_likely_rigify = any(check(bone_names) for check in rigify_specific_indicators)

    if is_likely_rigify:
        mapping = RIGIFY_BASE_MAP.copy()
        # Rigify 手指映射
        for finger_base, finger_ue_name in zip(["thumb", "index", "middle", "ring", "pinky"], ["thumb", "index", "middle", "ring", "pinky"]):
            for i, part in enumerate([".01", ".02", ".03"], start=1):
                if finger_base == "thumb":
                    left_original = f"thumb{part}.L"
                    right_original = f"thumb{part}.R"
                else:
                    left_original = f"f_{finger_base}{part}.L"
                    right_original = f"f_{finger_base}{part}.R"
                new_name = f"{finger_ue_name}_{i:02d}"
                mapping[left_original] = f"{new_name}_l"
                mapping[right_original] = f"{new_name}_r"
        return "Rigify", mapping
    else:
        # 如果不是 Mixamo 也不是 Rigify，则认为是 VRM (或其他使用 .L/.R 的格式)
        # VRM 手指映射
        mapping = VRM_BASE_MAP.copy()
        for finger_base, finger_ue_name in zip(["thumb", "index", "middle", "ring", "little"], ["thumb", "index", "middle", "ring", "pinky"]): # little -> pinky
            for i, part in enumerate(["_proximal", "_intermediate", "_distal"], start=1):
                left_original = f"{finger_base}{part}.L"
                right_original = f"{finger_base}{part}.R"
                new_name = f"{finger_ue_name}_{i:02d}"
                mapping[left_original] = f"{new_name}_l"
                mapping[right_original] = f"{new_name}_r"
        return "VRM", mapping

def find_chest_spine_number(edit_bones, initial_mapping):
    existing_spines_in_mapping = [name for name in initial_mapping.values() if name.startswith("spine_")]
    existing_spines_in_bones = [name for name in edit_bones.keys() if name.startswith("spine_") and name != "spine_00"]
    all_existing_spines = set(existing_spines_in_mapping + existing_spines_in_bones)
    existing_spines_list = sorted(list(all_existing_spines))
    if existing_spines_list:
        last_existing_spine = existing_spines_list[-1]
        match = re.match(r"spine_(\d+)", last_existing_spine)
        if match:
            last_num = int(match.group(1))
            return f"spine_{last_num + 1:02d}"
    return "spine_02"

def find_rigify_spine_mapping(edit_bones):
    mapping = {}
    for i in range(1, 10):
        rigify_name = f"spine.{i:03d}"
        if rigify_name in edit_bones:
            mapping[rigify_name] = f"spine_{i+1:02d}"
        else:
            break
    return mapping

def standardize_bone_name(name):
    standardized = name.replace('.L', '_l').replace('.R', '_r')
    standardized = re.sub(r'\.(\d+)', r'_\1', standardized)
    standardized = standardized.lower()
    standardized = re.sub(r'_+', '_', standardized)
    return standardized

def rename_armature_to_ue_standard_and_remove_mixamo_ends():
    obj = bpy.context.active_object
    if not obj or obj.type != 'ARMATURE':
        print("错误: 请先选择一个骨架物体。")
        return

    edit_bones = obj.data.edit_bones
    skeleton_type, initial_mapping = get_bone_mapping_and_type(edit_bones)
    print(f"检测到骨架类型: {skeleton_type}")

    # 处理类型特定的动态映射
    final_mapping = initial_mapping.copy()
    if skeleton_type == "VRM" and "chest" in edit_bones:
        chest_target = find_chest_spine_number(edit_bones, initial_mapping)
        final_mapping["chest"] = chest_target
        print(f"VRM 'chest' 骨骼将被重命名为 UE 的 '{chest_target}'")
    elif skeleton_type == "Rigify":
        final_mapping.update(find_rigify_spine_mapping(edit_bones))

    # 分离操作
    rename_pairs = []
    bones_to_delete = []
    bones_to_standardize = []

    if skeleton_type == "Mixamo":
        for original_name, target_name in final_mapping.items():
            if original_name in edit_bones:
                rename_pairs.append((original_name, target_name))
            else:
                print(f"{skeleton_type} 骨骼 '{original_name}' 不存在，跳过。")

        for bone in edit_bones:
            if bone.name.startswith("mixamorig:LeftHand") or bone.name.startswith("mixamorig:RightHand"):
                match = re.match(r"mixamorig:(Left|Right)Hand(\w+)(\d+)", bone.name)
                if match and match.group(3) == "4":
                    bones_to_delete.append(bone.name)
            elif (bone.name.endswith("_End") or bone.name.endswith("End")) and len(bone.children) == 0:
                bones_to_delete.append(bone.name)
    else: # VRM, Rigify, Unknown
        for original_name, target_name in final_mapping.items():
            if original_name in edit_bones:
                rename_pairs.append((original_name, target_name))
            else:
                print(f"{skeleton_type} 骨骼 '{original_name}' 不存在，跳过。")

    # 收集未映射的骨骼用于标准化
    all_mapped_names = set(final_mapping.keys())
    for bone_name in edit_bones.keys():
        if bone_name not in all_mapped_names:
            is_mixamo_end = (
                bone_name.startswith("mixamorig:LeftHand") or
                bone_name.startswith("mixamorig:RightHand") or
                bone_name.endswith("_End") or bone_name.endswith("End")
            )
            if skeleton_type == "Mixamo" and is_mixamo_end:
                continue
            else:
                standardized_name = standardize_bone_name(bone_name)
                if standardized_name != bone_name and standardized_name not in edit_bones:
                    bones_to_standardize.append((bone_name, standardized_name))

    # 执行操作
    was_edit_mode = bpy.context.mode == 'EDIT_ARMATURE'
    if not was_edit_mode:
        bpy.ops.object.mode_set(mode='EDIT')

    for old_name, new_name in rename_pairs:
        if old_name in edit_bones:
            print(f"正在重命名: {old_name} -> {new_name}")
            edit_bones[old_name].name = new_name

    for old_name, new_name in bones_to_standardize:
        if old_name in edit_bones and new_name not in edit_bones:
            print(f"正在标准化格式: {old_name} -> {new_name}")
            edit_bones[old_name].name = new_name
        elif new_name in edit_bones:
             print(f"警告: 标准化时目标名称 '{new_name}' 已存在，跳过 '{old_name}'。")

    for bone_name in bones_to_delete:
        if bone_name in edit_bones:
            edit_bones.remove(edit_bones[bone_name])
            print(f"已删除 Mixamo 末端骨骼: {bone_name}")

    if not was_edit_mode:
        bpy.ops.object.mode_set(mode='OBJECT')

    print("骨骼重命名、格式统一和 Mixamo 末端骨骼删除完成。")

# 执行函数
rename_armature_to_ue_standard_and_remove_mixamo_ends()