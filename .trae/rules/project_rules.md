1. 数据处理请使用conda虚拟环境 conda activate opensky
2. 命令行在ubuntu18.04的一个容器内运行,没有sudo权限，默认root用户
3. 当前服务器80核心CPU，512GB内存，8张32GB显存的v100显卡
4. 深度学习训练和测试，请使用conda activate Time-MoE 
5. 编写python的数据处理程序，一定考虑多进程。
6. 请不要随便在项目主目录创建py文件，python文件都要放在相关的目录下，如果没有就创建目录。测试用途的python文件放在test_python目录下。
7. 飞行轨迹的所有清洗好的数据，parquet格式，365个文件，在路径：/workspace/aircraft_trajectory/team_likable_jelly/perfect_trajectories，这是raw数据的一个子集，并非全部轨迹数据。
8. shm限制为64mb，必须设置dataloader的num_workers = 0，考虑8张v100显卡，可以考虑使用分布式数据并行训练，缓解问题。
9. 更新代码只有，记得更新对应的markdown文件，保持更改的可追踪性，可记忆性。
10. 不要轻易直接更改现有代码，请给出详细方案，我同意后再更改代码
