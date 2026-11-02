import pandas as pd
from flask import Flask, request, render_template, session
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import os
import time
from config import connect

app = Flask(__name__)

app.secret_key = "weather_project_secret_key"
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0

UPLOAD_FOLDER = "uploads"
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs("static/charts", exist_ok=True)


def create_charts(monthly):

    os.makedirs("static/charts", exist_ok=True)

    plt.figure(figsize=(8, 5))
    plt.plot(
        monthly["month"],
        monthly["average_temperature"],
        marker="o",
        color="#ff8c42",
        linewidth=3,
        markersize=8
    )
    plt.title("Monthly Average Temperature")
    plt.xlabel("Month")
    plt.ylabel("Temperature (°C)")
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.savefig("static/charts/temperature.png")
    plt.close()

    plt.figure(figsize=(8, 5))
    plt.plot(
        monthly["month"],
        monthly["average_humidity"],
        marker="o",
        color="#ff8c42",
        linewidth=3,
        markersize=8
    )
    plt.title("Monthly Average Humidity")
    plt.xlabel("Month")
    plt.ylabel("Humidity (%)")
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.savefig("static/charts/humidity.png")
    plt.close()

    plt.figure(figsize=(8, 5))
    plt.plot(
        monthly["month"],
        monthly["total_rainfall"],
        marker="o",
        color="#ff8c42",
        linewidth=3,
        markersize=8
    )
    plt.title("Monthly Total Rainfall")
    plt.xlabel("Month")
    plt.ylabel("Rainfall (mm)")
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.savefig("static/charts/rainfall.png")
    plt.close()


def get_uploaded_data(selected_city=None):

    uploaded_record_ids = session.get(
        "uploaded_record_ids",
        []
    )

    if not uploaded_record_ids:
        return None

    connection = connect()

    placeholders = ",".join(
        ["%s"] * len(uploaded_record_ids)
    )

    query = f"""
        SELECT
            observation_date,
            location,
            temperature,
            humidity,
            rainfall
        FROM weather_records
        WHERE record_id IN ({placeholders})
    """

    df = pd.read_sql(
        query,
        connection,
        params=uploaded_record_ids
    )

    connection.close()

    df["observation_date"] = pd.to_datetime(
        df["observation_date"]
    )

    if selected_city:
        df = df[
            df["location"] == selected_city
        ]

    return df


@app.route("/")
def dashboard():
    return render_template("dashboard.html")


@app.route("/upload", methods=["POST"])
def upload():

    files = request.files.getlist("files")

    if not files or all(
        file.filename == ""
        for file in files
    ):
        return "Please select at least one CSV file."

    uploaded_record_ids = []

    total_rows = 0
    total_valid = 0
    total_missing = 0
    total_invalid = 0
    total_duplicates = 0

    missing_by_column = {}
    uploaded_files = []

    required_columns = [
        "observation_date",
        "location",
        "temperature",
        "humidity",
        "rainfall"
    ]

    connection = connect()
    cursor = connection.cursor()

    try:

        for file in files:

            if file.filename == "":
                continue

            if not file.filename.lower().endswith(".csv"):
                continue

            file_path = os.path.join(
                app.config["UPLOAD_FOLDER"],
                file.filename
            )

            file.save(file_path)

            try:
                df = pd.read_csv(file_path)
            except Exception:
                continue

            uploaded_files.append(
                file.filename
            )

            total_rows += len(df)

            missing_columns = [
                column
                for column in required_columns
                if column not in df.columns
            ]

            if missing_columns:
                continue

            for column in required_columns:

                original_missing = int(
                    df[column].isna().sum()
                )

                missing_by_column[column] = (
                    missing_by_column.get(
                        column,
                        0
                    )
                    + original_missing
                )

            df["observation_date"] = pd.to_datetime(
                df["observation_date"],
                errors="coerce"
            )

            df["temperature"] = pd.to_numeric(
                df["temperature"],
                errors="coerce"
            )

            df["humidity"] = pd.to_numeric(
                df["humidity"],
                errors="coerce"
            )

            df["rainfall"] = pd.to_numeric(
                df["rainfall"],
                errors="coerce"
            )

            missing_mask = (
                df["observation_date"].isna()
                | df["location"].isna()
                | (
                    df["location"]
                    .astype(str)
                    .str.strip()
                    == ""
                )
                | df["temperature"].isna()
                | df["humidity"].isna()
                | df["rainfall"].isna()
            )

            total_missing += int(
                missing_mask.sum()
            )

            invalid_mask = (
                (df["humidity"] < 0)
                | (df["humidity"] > 100)
                | (df["rainfall"] < 0)
            )

            total_invalid += int(
                (
                    invalid_mask
                    & ~missing_mask
                ).sum()
            )

            valid_data = df[
                ~missing_mask
                & ~invalid_mask
            ].copy()

            total_valid += len(valid_data)

            duplicate_mask = valid_data.duplicated(
                subset=[
                    "observation_date",
                    "location",
                    "temperature",
                    "humidity",
                    "rainfall"
                ],
                keep=False
            )

            total_duplicates += int(
                duplicate_mask.sum()
            )

            for _, row in valid_data.iterrows():

                observation_date = row[
                    "observation_date"
                ].date()

                location = str(
                    row["location"]
                ).strip()

                temperature = float(
                    row["temperature"]
                )

                humidity = float(
                    row["humidity"]
                )

                rainfall = float(
                    row["rainfall"]
                )

                cursor.execute(
                    """
                    SELECT record_id
                    FROM weather_records
                    WHERE observation_date = %s
                    AND location = %s
                    AND temperature = %s
                    AND humidity = %s
                    AND rainfall = %s
                    """,
                    (
                        observation_date,
                        location,
                        temperature,
                        humidity,
                        rainfall
                    )
                )

                existing = cursor.fetchone()

                if existing:

                    uploaded_record_ids.append(
                        existing[0]
                    )

                else:

                    cursor.execute(
                        """
                        INSERT INTO weather_records
                        (
                            observation_date,
                            location,
                            temperature,
                            humidity,
                            rainfall
                        )
                        VALUES (%s, %s, %s, %s, %s)
                        """,
                        (
                            observation_date,
                            location,
                            temperature,
                            humidity,
                            rainfall
                        )
                    )

                    uploaded_record_ids.append(
                        cursor.lastrowid
                    )

        connection.commit()

    except Exception as e:

        connection.rollback()

        print(
            "UPLOAD ERROR:",
            e
        )

        cursor.close()
        connection.close()

        return render_template(
            "error.html",
            message=f"Upload Error: {e}"
        )

    cursor.close()
    connection.close()

    session["uploaded_record_ids"] = (
        uploaded_record_ids
    )

    if not uploaded_record_ids:

        return render_template(
            "error.html",
            message="No valid weather records were found in the uploaded files."
        )

    return render_template(
        "upload_result.html",
        valid_count=total_valid,
        invalid_count=total_invalid,
        missing_count=total_missing,
        duplicate_count=total_duplicates,
        total_rows=total_rows,
        missing_by_column=missing_by_column,
        uploaded_files=uploaded_files
    )


@app.route("/analysis")
def analysis():

    selected_city = request.args.get(
        "city",
        ""
    )

    all_data = get_uploaded_data()

    if all_data is None or all_data.empty:

        return render_template(
            "error.html",
            message="Please upload a CSV file before viewing analysis."
        )

    cities = sorted(
        all_data["location"]
        .dropna()
        .unique()
        .tolist()
    )

    if selected_city:

        df = all_data[
            all_data["location"]
            == selected_city
        ].copy()

    else:

        df = all_data.copy()

    if df.empty:

        return render_template(
            "error.html",
            message="No weather data is available for the selected city."
        )

    total_records = len(df)

    average_temperature = round(
        df["temperature"].mean(),
        2
    )

    average_humidity = round(
        df["humidity"].mean(),
        2
    )

    total_rainfall = round(
        df["rainfall"].sum(),
        2
    )

    highest_temperature = round(
        df["temperature"].max(),
        2
    )

    lowest_temperature = round(
        df["temperature"].min(),
        2
    )

    temperature_range = round(
        highest_temperature
        - lowest_temperature,
        2
    )

    df["month_number"] = (
        df["observation_date"]
        .dt.month
    )

    monthly = (
        df.groupby("month_number")
        .agg(
            average_temperature=(
                "temperature",
                "mean"
            ),
            maximum_temperature=(
                "temperature",
                "max"
            ),
            minimum_temperature=(
                "temperature",
                "min"
            ),
            average_humidity=(
                "humidity",
                "mean"
            ),
            total_rainfall=(
                "rainfall",
                "sum"
            )
        )
        .reset_index()
    )

    monthly = monthly.round(2)

    month_names = {
        1: "January",
        2: "February",
        3: "March",
        4: "April",
        5: "May",
        6: "June",
        7: "July",
        8: "August",
        9: "September",
        10: "October",
        11: "November",
        12: "December"
    }

    monthly["month"] = (
        monthly["month_number"]
        .map(month_names)
    )

    monthly = monthly[
        [
            "month",
            "average_temperature",
            "maximum_temperature",
            "minimum_temperature",
            "average_humidity",
            "total_rainfall"
        ]
    ]

    hottest_month = monthly.loc[
        monthly["average_temperature"]
        .idxmax(),
        "month"
    ]

    coolest_month = monthly.loc[
        monthly["average_temperature"]
        .idxmin(),
        "month"
    ]

    highest_humidity_month = monthly.loc[
        monthly["average_humidity"]
        .idxmax(),
        "month"
    ]

    highest_rainfall_month = monthly.loc[
        monthly["total_rainfall"]
        .idxmax(),
        "month"
    ]

    print(
        "\nMONTHLY WEATHER ANALYSIS"
    )

    print(monthly)

    create_charts(monthly)

    chart_version = int(
        time.time()
    )

    return render_template(
        "analysis.html",
        total_records=total_records,
        average_temperature=average_temperature,
        average_humidity=average_humidity,
        total_rainfall=total_rainfall,
        highest_temperature=highest_temperature,
        lowest_temperature=lowest_temperature,
        temperature_range=temperature_range,
        hottest_month=hottest_month,
        coolest_month=coolest_month,
        highest_humidity_month=highest_humidity_month,
        highest_rainfall_month=highest_rainfall_month,
        monthly=monthly.to_dict(
            "records"
        ),
        chart_version=chart_version,
        cities=cities,
        selected_city=selected_city
    )


@app.route("/city-comparison")
def city_comparison():

    df = get_uploaded_data()

    if df is None or df.empty:

        return render_template(
            "error.html",
            message="Please upload a CSV file before viewing city comparison."
        )

    city_data = (
        df.groupby("location")
        .agg(
            average_temperature=(
                "temperature",
                "mean"
            ),
            average_humidity=(
                "humidity",
                "mean"
            ),
            total_rainfall=(
                "rainfall",
                "sum"
            ),
            highest_temperature=(
                "temperature",
                "max"
            ),
            lowest_temperature=(
                "temperature",
                "min"
            )
        )
        .reset_index()
    )

    city_data["temperature_range"] = (
        city_data["highest_temperature"]
        - city_data["lowest_temperature"]
    )

    city_data = city_data.round(2)

    cities = city_data[
        "location"
    ].tolist()

    os.makedirs(
        "static/charts",
        exist_ok=True
    )

    plt.figure(figsize=(8, 5))

    plt.bar(
        city_data["location"],
        city_data["average_temperature"],
        color="#ff8c42"
    )

    plt.title(
        "City-wise Average Temperature"
    )

    plt.xlabel("City")

    plt.ylabel(
        "Temperature (°C)"
    )

    plt.xticks(rotation=45)

    plt.tight_layout()

    plt.savefig(
        "static/charts/city_temperature.png"
    )

    plt.close()

    plt.figure(figsize=(8, 5))

    plt.bar(
        city_data["location"],
        city_data["average_humidity"],
        color="#ff8c42"
    )

    plt.title(
        "City-wise Average Humidity"
    )

    plt.xlabel("City")

    plt.ylabel(
        "Humidity (%)"
    )

    plt.xticks(rotation=45)

    plt.tight_layout()

    plt.savefig(
        "static/charts/city_humidity.png"
    )

    plt.close()

    plt.figure(figsize=(8, 5))

    plt.bar(
        city_data["location"],
        city_data["total_rainfall"],
        color="#ff8c42"
    )

    plt.title(
        "City-wise Total Rainfall"
    )

    plt.xlabel("City")

    plt.ylabel(
        "Rainfall (mm)"
    )

    plt.xticks(rotation=45)

    plt.tight_layout()

    plt.savefig(
        "static/charts/city_rainfall.png"
    )

    plt.close()

    chart_version = int(
        time.time()
    )

    return render_template(
        "city_comparison.html",
        cities=city_data.to_dict(
            "records"
        ),
        chart_version=chart_version
    )


if __name__ == "__main__":
    app.run(debug=True)
