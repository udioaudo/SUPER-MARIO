2.1确定需求
目标:我希望用Python开发一个fc模拟器，最终能跑超级玛丽。现在帮我完成需求文档。
输出:请在doc文件夹下生成需求文档doc/SUPER MARIO.md。
步骤:我不了解任何fc模拟器的知识。请使用提问的方式帮助我确认需求。不要猜测我的意图。任何不明确的地方都必须都向我提问。

2.2设计
2.2.1概要设计--划分模块（可能包含在需求文档：功能需求）
目标:根据需求文档生成概要设计文档。
输入:需求文档 doc/SUPER MARIO.md。
输出:概要设计文档 doc/high-level-design.md。
步骤:根据需求文档的内容，划分出模块，识别模块与模块之间的关系。生成概要设计文档。不要猜测我的意图。任何不明确的地方都必须都向我提问。
2.2.2详细设计--实现细节
目标:根据需求文档生成详细设计文档。
输入:需求文档 doc/SUPER MARIO.md。
输出:详细设计文档 doc/detailed-design.md。
步骤:根据需求文档的内容，根据里面划分出的模块编写详细设计文档。模块与模块之间尽量保持相互独立，可以独立进行测试。不要猜测我的意图。任何不明确的地方都必须都向我提问。

2.3划分任务
目标：为每个模块划分最小可执行任务
输入：
需求文档 doc/SUPER MARIO.md
详细设计 doc/detailed-design.md
输出：任务列表
doc/tasks/<module-name>.md(每个模块对应一个)
doc/tasks/progress.md(总体进度)
步骤：根据需求文档和详细设计。为每一个模块生成Vibe Coding用的最小任务。
每个模块对应一个<module-name>.md
用check list表示子任务是否完成。
progress.md中用check list表示模块是否已经完成

2.4实现
目标:生成Vibe Coding用的Prompt
输入:
①需求文档 doc/SUPER MARIO.md
②详细设计 doc/detailed-design.md
③任务划分 doc/tasks
输出:
doc/prompt.md
步骤:
①阅读输入信息，了解当前要实现的工程生成doc/prompt.md作为Vibe Coding的起始Prompt。
②主Agent，用来跟踪整体的进度，
③主Agent生成子Agent，用来实现每一个模块，并完成测试整个过程不会有人工参与。
④代码必须有完整的pytest单元测试，并通过mypy和ruff检测。
⑤生成prompt过程中，如果有任何不明确的地方都必须都向我提问。
