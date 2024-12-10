from flask import Flask, request, render_template
import requests
from config import (
    ACCUWEATHER_API_KEY, ACCUWEATHER_GEOCODING_URL,
    LANGUAGE, METRIC, API_REQUEST_TIMEOUT
)

app = Flask(__name__)


def check_bad_weather(temperature, wind_speed, precipitation_probability):
    if temperature < 0 or temperature > 35 or wind_speed > 50 or precipitation_probability > 70:
        return "Ой-ой, погода плохая"
    return "Погода — супер"


def get_weather_icon(temperature, wind_speed, precipitation_probability):
    if precipitation_probability > 70:
        return "rainy.png"
    if temperature < 0:
        return "snowy.png"
    if temperature > 35:
        return "sunny.png"
    if wind_speed > 50:
        return "cloudy.png"
    return "sunny.png"


def map_forecast_to_icon(day_condition):
    condition = day_condition.lower()
    if 'снег' in condition:
        return 'snowy.png'
    elif 'дождь' in condition or 'ливень' in condition or 'морось' in condition:
        return 'rainy.png'
    elif 'облачно' in condition or 'пасмурно' in condition:
        return 'cloudy.png'
    else:
        return 'sunny.png'


def get_coordinates(city_name):
    params = {
        'apikey': ACCUWEATHER_API_KEY,
        'q': city_name,
        'language': LANGUAGE,
    }

    try:
        response = requests.get(ACCUWEATHER_GEOCODING_URL, params=params, timeout=API_REQUEST_TIMEOUT)
        response.raise_for_status()
        data = response.json()

        if not data:
            raise ValueError("Город не найден. Убедитесь, что название введено корректно.")

        lat = data[0]['GeoPosition']['Latitude']
        lon = data[0]['GeoPosition']['Longitude']
        return lat, lon

    except requests.exceptions.RequestException as e:
        raise ValueError(f"Ошибка подключения к серверу: {e}")
    except (KeyError, IndexError):
        raise ValueError("Невозможно получить координаты для заданного города.")


def get_weather(latitude, longitude):
    params = {
        'apikey': ACCUWEATHER_API_KEY,
        'language': LANGUAGE,
        'details': 'true',
    }

    location_key = get_location_key(latitude, longitude)

    if not location_key:
        raise ValueError("Невозможно получить ключ локации. Попробуйте другой город.")

    weather_url = f"https://dataservice.accuweather.com/currentconditions/v1/{location_key}"

    try:
        response = requests.get(weather_url, params=params, timeout=API_REQUEST_TIMEOUT)
        response.raise_for_status()
        data = response.json()

        if not data:
            raise ValueError("Данные о погоде недоступны.")

        weather = data[0]

        if METRIC:
            temperature = weather['Temperature']['Metric']['Value']
            wind_speed = weather['Wind']['Speed']['Metric']['Value']
        else:
            temperature = weather['Temperature']['Imperial']['Value']
            wind_speed = weather['Wind']['Speed']['Imperial']['Value']

        humidity = weather.get('RelativeHumidity', 50)
        precipitation_probability = weather.get('PrecipitationProbability', 0)

        return {
            'temperature': temperature,
            'wind_speed': wind_speed,
            'humidity': humidity,
            'precipitation_probability': precipitation_probability
        }

    except requests.exceptions.RequestException as e:
        raise ValueError(f"Ошибка доступа к погодному API: {e}")
    except KeyError:
        raise ValueError("Невозможно распознать структуру данных о погоде.")


def get_forecast(location_key):
    forecast_url = f"https://dataservice.accuweather.com/forecasts/v1/daily/5day/{location_key}"

    params = {
        'apikey': ACCUWEATHER_API_KEY,
        'language': LANGUAGE,
        'metric': METRIC
    }

    try:
        response = requests.get(forecast_url, params=params, timeout=API_REQUEST_TIMEOUT)
        response.raise_for_status()
        data = response.json()

        if not data or 'DailyForecasts' not in data:
            raise ValueError("Данные прогноза погоды недоступны.")

        forecasts = []
        for day in data['DailyForecasts']:
            day_condition = day['Day']['IconPhrase']

            day_icon = map_forecast_to_icon(day_condition)

            forecast = {
                'date': day['Date'][:10],
                'min_temp': day['Temperature']['Minimum']['Value'],
                'max_temp': day['Temperature']['Maximum']['Value'],
                'day_icon': day_icon,
                'precipitation': day.get('Day', {}).get('PrecipitationProbability', 0)
            }
            forecasts.append(forecast)

        return forecasts

    except requests.exceptions.RequestException as e:
        raise ValueError(f"Ошибка доступа к API прогноза погоды: {e}")
    except KeyError:
        raise ValueError("Невозможно распознать структуру данных прогноза погоды.")


def get_location_key(latitude, longitude):
    url = "https://dataservice.accuweather.com/locations/v1/cities/geoposition/search"

    params = {
        'apikey': ACCUWEATHER_API_KEY,
        'q': f"{latitude},{longitude}",
        'language': LANGUAGE
    }

    try:
        response = requests.get(url, params=params, timeout=API_REQUEST_TIMEOUT)
        response.raise_for_status()
        data = response.json()
        if 'Key' in data:
            return data['Key']
        return None
    except requests.exceptions.RequestException:
        return None


@app.route('/', methods=['GET'])
def index():
    return render_template('index.html')


@app.route('/result', methods=['POST'])
def result():
    start_city = request.form.get('start')
    end_city = request.form.get('end')

    if not start_city or not end_city:
        return render_template('error.html', error_message="Поля ввода маршрута не должны быть пустыми.")

    try:
        start_coords = get_coordinates(start_city)
        end_coords = get_coordinates(end_city)

        start_location_key = get_location_key(start_coords[0], start_coords[1])
        end_location_key = get_location_key(end_coords[0], start_coords[1])

        if not start_location_key or not end_location_key:
            raise ValueError("Невозможно получить ключи локации для одного из городов.")

        start_weather = get_weather(*start_coords)
        end_weather = get_weather(*end_coords)

        start_forecast = get_forecast(start_location_key)
        end_forecast = get_forecast(end_location_key)

        start_assessment = check_bad_weather(
            start_weather['temperature'],
            start_weather['wind_speed'],
            start_weather['precipitation_probability']
        )

        end_assessment = check_bad_weather(
            end_weather['temperature'],
            end_weather['wind_speed'],
            end_weather['precipitation_probability']
        )

        start_icon = get_weather_icon(
            start_weather['temperature'],
            start_weather['wind_speed'],
            start_weather['precipitation_probability']
        )

        end_icon = get_weather_icon(
            end_weather['temperature'],
            end_weather['wind_speed'],
            end_weather['precipitation_probability']
        )

        overall_result = {
            'start': {
                'city': start_city,
                'assessment': start_assessment,
                'icon': start_icon,
                'current_weather': start_weather,
                'forecast': start_forecast
            },
            'end': {
                'city': end_city,
                'assessment': end_assessment,
                'icon': end_icon,
                'current_weather': end_weather,
                'forecast': end_forecast
            }
        }

        return render_template('result.html', overall_result=overall_result)

    except ValueError as e:
        return render_template('error.html', error_message=str(e))
    except Exception:
        return render_template('error.html', error_message="Произошла непредвиденная ошибка. Попробуйте снова.")


if __name__ == '__main__':
    app.run(debug=True)
