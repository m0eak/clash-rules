import os
import re
import requests
from collections import defaultdict
from datetime import datetime
import hashlib

# 配置文件路径
CONFIG_FILE = 'rule_sources.conf'
OUTPUT_DIR = 'rule-provider'

def read_config(config_file):
    """读取配置文件并按类别分组 URL。"""
    categories = {}
    current_category = None
    
    print(f"开始读取配置文件: {config_file}")
    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            content = f.read()
            print(f"配置文件内容:\n{content}")
            
            for line in content.split('\n'):
                line = line.strip()
                print(f"处理行: '{line}'")
                
                # 空行跳过
                if not line:
                    print("  跳过空行")
                    continue
                
                # 识别类别行 (以 ## 开头)
                if line.startswith('## '):
                    current_category = line[3:].strip()  # 去掉 '## ' 前缀
                    print(f"  找到类别: '{current_category}'")
                    categories[current_category] = []
                # 识别普通注释行 (以 # 开头但不是 ##)
                elif line.startswith('#') and not line.startswith('##'):
                    print("  跳过注释行")
                    continue
                # 识别URL行
                elif current_category is not None and (line.startswith('http://') or line.startswith('https://')):
                    print(f"  添加URL到类别 '{current_category}': {line}")
                    categories[current_category].append(line)
                else:
                    print(f"  无法识别的行: '{line}'")
        
        print(f"解析完成，找到类别: {list(categories.keys())}")
        return categories
    except Exception as e:
        print(f"读取配置文件时出错: {e}")
        return {}

def download_rule(url):
    """从 URL 下载规则内容。"""
    try:
        print(f"下载规则: {url}")
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        content = response.text
        print(f"成功下载，内容长度: {len(content)} 字符")
        return content
    except Exception as e:
        print(f"下载 {url} 时出错: {e}")
        return None

def parse_rules(content):
    """从内容中解析规则。"""
    if not content:
        return {}
    
    # 规则类型计数器
    rule_types = {
        'DOMAIN': [],
        'DOMAIN-SUFFIX': [],
        'DOMAIN-KEYWORD': [],
        'IP-CIDR': [],
        'IP-ASN': [],
        'USER-AGENT': [],
        'URL-REGEX': [],
        'PROCESS-NAME': [],
        'TOTAL': 0
    }
    
    # 解析每一行
    for line in content.split('\n'):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        
        # 识别规则类型
        for rule_type in rule_types.keys():
            if rule_type != 'TOTAL' and line.startswith(rule_type):
                rule_types[rule_type].append(line)
                rule_types['TOTAL'] += 1
                break
    
    return rule_types

def merge_rules(sources, category_name):
    """合并来自多个源的规则。"""
    merged_rules = {
        'DOMAIN': set(),
        'DOMAIN-SUFFIX': set(),
        'DOMAIN-KEYWORD': set(),
        'IP-CIDR': set(),
        'IP-ASN': set(),
        'USER-AGENT': set(),
        'URL-REGEX': set(),
        'PROCESS-NAME': set()
    }
    
    # 下载并解析每个源的规则
    source_urls = []
    for url in sources:
        content = download_rule(url)
        if content:
            source_urls.append(url)
            rules = parse_rules(content)
            
            # 合并规则
            for rule_type, rule_list in rules.items():
                if rule_type != 'TOTAL':
                    for rule in rule_list:
                        merged_rules[rule_type].add(rule)
    
    # 生成输出文件内容
    output_content = []
    
    # 添加源 URL 作为注释
    for url in source_urls:
        output_content.append(f"# {url}")
    
    # 添加元数据
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    output_content.append(f"# NAME: {category_name}")
    output_content.append(f"# AUTHOR: Generated by GitHub Action")
    output_content.append(f"# REPO: https://github.com/your-username/your-repo")
    output_content.append(f"# UPDATED: {current_time}")
    
    # 添加规则类型计数
    total_rules = 0
    for rule_type, rules in merged_rules.items():
        if rules:
            output_content.append(f"# {rule_type}: {len(rules)}")
            total_rules += len(rules)
    
    output_content.append(f"# TOTAL: {total_rules}")
    
    # 添加规则
    for rule_type, rules in merged_rules.items():
        if rules:
            for rule in sorted(rules):
                output_content.append(rule)
    
    return "\n".join(output_content)

def main():
    """更新所有规则文件的主函数。"""
    # 确保输出目录存在
    if not os.path.exists(OUTPUT_DIR):
        print(f"创建输出目录 {OUTPUT_DIR}")
        os.makedirs(OUTPUT_DIR, exist_ok=True)
    else:
        print(f"输出目录 {OUTPUT_DIR} 已存在")
    
    # 显示当前工作目录
    print(f"当前工作目录: {os.getcwd()}")
    
    # 读取配置
    print(f"读取配置文件 {CONFIG_FILE}")
    categories = read_config(CONFIG_FILE)
    print(f"找到 {len(categories)} 个类别: {', '.join(categories.keys())}")
    
    # 跟踪是否有任何文件被更新
    any_file_updated = False
    
    # 处理每个类别
    for category, urls in categories.items():
        print(f"正在处理 {category}...")
        merged_content = merge_rules(urls, category)
        
        # 写入输出文件
        output_file = os.path.join(OUTPUT_DIR, f"{category}.list")
        
        # 检查文件是否存在以及内容是否相同
        file_exists = os.path.exists(output_file)
        content_identical = False
        
        if file_exists:
            try:
                with open(output_file, 'r') as f:
                    existing_content = f.read()
                content_identical = existing_content == merged_content
            except Exception as e:
                print(f"读取现有文件时出错: {e}")
        
        if not file_exists or not content_identical:
            print(f"规则内容已更改，写入文件 {output_file}")
            with open(output_file, 'w') as f:
                f.write(merged_content)
            any_file_updated = True
            print(f"已更新 {output_file}")
        else:
            print(f"规则内容未变化，保持 {output_file} 不变")
    
    # 输出总结
    if any_file_updated:
        print("已完成规则更新，有文件内容发生变化")
    else:
        print("已完成规则检查，所有规则均为最新状态，没有文件被更改")
        
    # 创建一个标记文件，用于工作流判断是否有实际更新
    with open('rules_updated.flag', 'w') as f:
        f.write('1' if any_file_updated else '0')

if __name__ == "__main__":
    main()
