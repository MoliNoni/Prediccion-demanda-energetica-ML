import type { Translate } from "../i18n/translations";
import { dataSplitFor } from "../lib/dataSplit";

type SplitBadgeProps = {
  t: Translate;
  targetDate: string;
};

const LABELS = {
  train: { label: "splitTrain", title: "splitTrainTitle" },
  validation: { label: "splitValidation", title: "splitValidationTitle" },
  test: { label: "splitTest", title: "splitTestTitle" },
} as const;

export function SplitBadge({ t, targetDate }: SplitBadgeProps) {
  const split = dataSplitFor(targetDate);
  return (
    <span className={`tag row-badge split-badge split-${split}`} title={t(LABELS[split].title)}>
      {t(LABELS[split].label)}
    </span>
  );
}
