# 巨潮资讯网公告信息抽取工具

从巨潮资讯网搜公告 → AI 自动提取你想要的任何信息 → 输出 Excel。不用写代码。

## 使用

### 有 Python

```bash
pip install -r requirements.txt
python app.py
```

### 没有 Python

下载 [Releases](../../releases) 里的 `巨潮公告提取工具.zip`，解压双击 `巨潮公告提取工具.exe`。

## 三步完成一次抽取

1. 填**关键词**和**日期**（如 `独立董事+辞职，2016-2018`）
2. 选场景填字段（如"高管离职 → 姓名、职位、辞职原因"），点生成 Prompt
3. 填 API Key（[DeepSeek](https://platform.deepseek.com) 充值获取）
4. 点 **一键运行全部**

## 内置场景

高管离职 / 资产收购与出售 / 大股东增减持 / 重大合同 / 违规处罚 / 分红方案 / 业绩预告 / 诉讼仲裁 / 会计师事务所变更 / 股票回购 / 自定义

## 输出

每个任务在 `data/` 下生成独立文件夹，Excel 含两个 Sheet：
- AI提取结果
- 已筛选排除

## License

MIT
