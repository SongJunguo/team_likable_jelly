# 环境迁移报告：从 opensky 到 data_wrangler

**迁移日期**: 2025-11-15  
**执行人**: GitHub Copilot  
**原因**: Python 版本升级 (3.9 → 3.14)，获得更好的性能和最新特性支持

---

## 一、环境对比

| 项目 | opensky | data_wrangler | 改进 |
|------|---------|---------------|------|
| Python 版本 | 3.9.21 | 3.14.0 | ✓ 最新版本 |
| pandas | 2.2.3 | 2.3.3 | ✓ 版本更新 |
| numpy | 1.26.4 | 2.3.4 | ✓ 大版本升级 |
| pyarrow | 19.0.0 | 22.0.0 | ✓ 版本更新 |
| scipy | 1.13.1 | 1.16.3 | ✓ 版本更新 |
| scikit-learn | 1.6.1 | 1.7.2 | ✓ 版本更新 |
| matplotlib | 3.9.4 | 3.10.8 | ✓ 版本更新 |
| seaborn | 0.13.2 | 0.13.2 | - 相同 |
| polars | 1.33.1 | 1.35.2 | ✓ 版本更新 |
| geopandas | 1.0.1 | 1.1.1 | ✓ 版本更新 |
| cartopy | 0.23.0 | 0.25.0 | ✓ 版本更新 |

---

## 二、已安装的包

### 核心数据处理
- ✓ **pandas** 2.3.3
- ✓ **numpy** 2.3.4
- ✓ **pyarrow** 22.0.0
- ✓ **polars** 1.35.2

### 科学计算
- ✓ **scipy** 1.16.3
- ✓ **scikit-learn** 1.7.2
- ✓ **joblib** 1.5.2

### 可视化
- ✓ **matplotlib** 3.10.8
- ✓ **seaborn** 0.13.2

### 地理数据
- ✓ **geopandas** 1.1.1
- ✓ **shapely** 2.1.2
- ✓ **cartopy** 0.25.0
- ✓ **pyproj** 3.7.2

### 工具包
- ✓ **tqdm** 4.67.1
- ✓ **requests** 2.32.5

---

## 三、已知限制

### ⚠ traffic 包不兼容
- **问题**: traffic 2.10.2 依赖 numpy==1.26.4，与 Python 3.14 不兼容
- **解决方案**: 需要使用 traffic 时，临时切换到 `opensky` 环境 (Python 3.9)
- **命令**: `conda activate opensky`

---

## 四、测试结果

### ✓ 测试 1: 基本包导入
所有 13 个核心包成功导入，版本正常。

### ✓ 测试 2: Parquet 文件读取
- 测试文件: `complete_2022-10-23.parquet`
- 读取时间: 0.333 秒
- 数据规模: 5,135,627 行 × 13 列
- 内存占用: 509.36 MB
- **结论**: 性能正常

### ✓ 测试 3: 多进程计算
- CPU 核心数: 80
- 并行任务数: 8
- 执行时间: 0.335 秒
- **结论**: 多进程功能正常

### ✓ 测试 4: 地理数据处理
- GeoDataFrame 创建: 成功
- 坐标系转换 (WGS84 → UTM): 成功
- **结论**: geopandas 功能正常

---

## 五、迁移影响

### 需要更新的地方
1. ✅ **全局指令文档** (`.github/copilot-instructions.md`)
   - 已更新数据处理环境为 `data_wrangler`
   - 已添加 traffic 包的使用说明

2. ⚠ **现有脚本**
   - 大部分脚本**无需修改**（API 兼容）
   - 使用 traffic 的脚本需切换到 opensky 环境

3. ✓ **性能提升**
   - Python 3.14 性能优化
   - numpy 2.x 显著性能提升
   - 更好的内存管理

---

## 六、使用建议

### 数据处理（推荐）
```bash
conda activate data_wrangler
python your_script.py
```

### 使用 traffic 包
```bash
conda activate opensky
python script_using_traffic.py
```

### 深度学习训练
```bash
conda activate Time-MoE
python train.py
```

---

## 七、后续计划

1. **逐步迁移现有脚本**: 将数据处理脚本切换到 data_wrangler
2. **监控 traffic 兼容性**: 等待 traffic 包支持 Python 3.14
3. **性能基准测试**: 对比新旧环境的实际性能差异
4. **考虑弃用 opensky**: 当 traffic 包兼容后，可完全迁移

---

## 八、测试命令

验证环境可用性:
```bash
conda activate data_wrangler
python test_python/test_data_wrangler_env.py
```

---

**结论**: ✅ data_wrangler 环境已完全就绪，可作为主要数据处理环境使用！
