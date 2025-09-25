1. 数据处理请使用conda虚拟环境 conda activate opensky
2. 命令行在ubuntu18.04的一个容器内运行
3. 当前服务器80核心CPU，512GB内存，8张32GB显存的v100显卡
4. 路径 junguo_analysis_for_opensky2022、learn_python、trajectory_stitching这三个路径下面内容是我使用trae的sonnet4生产的分析文件，并非team likable jelly提供的官方代码。
5. 编写python的数据处理程序，一定考虑多进程。
6. 请不要随便在项目主目录创建py文件，python文件都要放在相关的目录下，如果没有就创建目录。测试用途的python文件放在test_python目录下。

