def compute_direct_metrics(direct_decisions):
    """计算直接判断模式的统计指标。"""
    total = len(direct_decisions)
    if total == 0:
        return {"total": 0, "accuracy": 0.0}

    accepted = sum(1 for item in direct_decisions if bool(item))
    accuracy = accepted / total
    return {"total": total, "accuracy": accuracy}


def compute_manual_metrics(manual_annotations):
    """计算人工输入模式的 accuracy / precision / recall / f1（macro）。"""
    if not manual_annotations:
        return {
            "total": 0,
            "accuracy": 0.0,
            "precision": 0.0,
            "recall": 0.0,
            "f1": 0.0,
        }

    y_true = [str(item.get("manual_result", "")).strip() for item in manual_annotations]
    y_pred = [str(item.get("llm_output", "")).strip() for item in manual_annotations]

    n = len(y_true)
    correct = sum(1 for true_v, pred_v in zip(y_true, y_pred) if true_v == pred_v)
    accuracy = correct / n if n > 0 else 0.0

    labels = sorted(set(y_true) | set(y_pred))
    precisions = []
    recalls = []
    f1_scores = []

    for label in labels:
        tp = sum(
            1
            for true_v, pred_v in zip(y_true, y_pred)
            if true_v == label and pred_v == label
        )
        fp = sum(
            1
            for true_v, pred_v in zip(y_true, y_pred)
            if true_v != label and pred_v == label
        )
        fn = sum(
            1
            for true_v, pred_v in zip(y_true, y_pred)
            if true_v == label and pred_v != label
        )

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = (
            (2 * precision * recall / (precision + recall))
            if (precision + recall) > 0
            else 0.0
        )

        precisions.append(precision)
        recalls.append(recall)
        f1_scores.append(f1)

    label_count = len(labels) if labels else 1
    precision_macro = sum(precisions) / label_count
    recall_macro = sum(recalls) / label_count
    f1_macro = sum(f1_scores) / label_count

    return {
        "total": n,
        "accuracy": accuracy,
        "precision": precision_macro,
        "recall": recall_macro,
        "f1": f1_macro,
    }
