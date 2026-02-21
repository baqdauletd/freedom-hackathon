import { parseCsv, fetchText } from "./client";
import type { Manager } from "./types";

const normalizeSkills = (value: string): string[] =>
  value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);

export const loadManagers = async (path = "/managers.csv"): Promise<Manager[]> => {
  const text = await fetchText(path);

  return parseCsv(text, (row, index) => {
    const name = row["ФИО"];
    return {
      id: `${name}-${index}`,
      name,
      role: row["Должность"],
      office: row["Офис"],
      skills: normalizeSkills(row["Навыки"]),
      currentLoad: Number(row["Количество обращений в работе"] || 0),
    };
  });
};
