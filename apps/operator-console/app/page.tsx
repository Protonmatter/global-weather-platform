import { requireChatGPTUser } from "./chatgpt-auth";
import WeatherConsole from "./components/weather-console";

export default async function Home() {
  const user = await requireChatGPTUser("/");
  return (
    <WeatherConsole
      operatorName={user.displayName}
      operatorEmail={user.email}
    />
  );
}
