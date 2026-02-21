import { parseCsv, fetchText } from "./client";
import type { Ticket } from "./types";

export const loadTickets = async (path = "/tickets.csv"): Promise<Ticket[]> => {
  const text = await fetchText(path);

  return parseCsv(text, (row) => ({
    id: row["GUID клиента"],
    gender: row["Пол клиента"],
    birthDate: row["Дата рождения"],
    description: row["Описание"],
    attachments: row["Вложения"],
    segment: (row["Сегмент клиента"] || "Mass") as Ticket["segment"],
    country: row["Страна"],
    region: row["Область"],
    city: row["Населённый пункт"],
    street: row["Улица"],
    house: row["Дом"],
  }));
};
