from __future__ import annotations


class ConceptEmbedder:
    """测试用确定性向量器：把同一概念的词映射到同一维度。

    只用于验证向量索引/混合检索的管线，不代表真实语义模型。
    """

    provider = "test"
    model = "concept-test-v1"
    DIM = 5
    CONCEPTS = [
        (("报销", "期限", "提交", "多久", "天", "钱", "报", "费用", "审批"), [1, 0, 0, 0, 0]),
        (("云剪辑", "导出", "格式", "视频", "mp4", "mov", "字幕"), [0, 1, 0, 0, 0]),
        (("年假", "休假", "带薪", "跨年", "结转"), [0, 0, 1, 0, 0]),
        (("差旅", "出差", "行程", "发票", "材料"), [0, 0, 0, 1, 0]),
        (("食堂", "开门", "吃饭"), [0, 0, 0, 0, 1]),
    ]

    def embed(self, texts: list[str], input_type: str | None = None) -> list[list[float]]:
        vectors = []
        for text in texts:
            lowered = text.lower()
            vector = [0.0] * self.DIM
            for keywords, weights in self.CONCEPTS:
                if any(keyword in lowered for keyword in keywords):
                    for index, weight in enumerate(weights):
                        vector[index] += weight
            vectors.append(vector)
        return vectors
